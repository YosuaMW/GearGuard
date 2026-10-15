"""POST /explain - penjelasan alert anomali (bahasa Inggris) oleh Qwen3.8-27B,
berlandaskan manual + riwayat perbaikan (RAG).

Bila LLM gagal, endpoint mengembalikan error (502) agar backend mempertahankan penjelasan
berbasis aturannya (docs/role3-ai.md: "If it fails, the existing rule-based explanation is kept").
"""
import json
import logging
import re
import time

from .config import Settings
from .llm import TokenFactoryClient, UpstreamError, extract_json, make_usage
from .rag import RagIndex
from .schemas import URGENCY_LEVELS, ExplainIn, ExplainOut, FeatureStat, SourceRef

log = logging.getLogger("ai.explain")

SYSTEM_PROMPT = f"""You are a maintenance assistant for factory supervisors and operators.
You receive an early-warning alert from sensors (current in A, vibration in g RMS, temperature in °C),
recent downtime events logged by operators, and numbered source excerpts from motor/pump manuals and
the plant's repair history, labelled [S1], [S2], ... Sources may be in Indonesian or English.

Rules:
1. Write in clear, plain ENGLISH (translate Indonesian sources). "summary" is at most 2 sentences:
   what deviates from normal (use the percentages given) and what that pattern is consistent with.
2. Ground causes and actions in the sources. Cite labels like [S1] inside "summary" or "actions" when you
   rely on a source. NEVER invent manual content, page numbers or section numbers. If the sources are empty
   or irrelevant, say so briefly, give only generic safe checks, and leave "sources_used" empty.
3. Do not claim certainty ("consistent with", "may indicate"). Do not recommend anything unsafe; if risk of
   fire, burning smell or smoke is mentioned, urgency is "inspect now".
4. "actions": 2 to 4 short imperative steps. "urgency" must be exactly one of {json.dumps(URGENCY_LEVELS)}.
5. Recent downtime events are context only; use them if they relate to the same fault.

Reply with ONLY valid JSON:
{{"summary": "...", "actions": ["..."], "urgency": "...", "sources_used": ["S1"]}}"""

_SENSOR = {
    "vib_rms": ("vibration", "g RMS"),
    "temp_c": ("temperature", "°C"),
    "current_a": ("current", "A"),
}
_TERMS = {
    "vib_rms": "getaran vibrasi vibration bearing bantalan balance alignment longgar loose bunyi noise mounting",
    "temp_c": "suhu panas temperature overheat pendinginan cooling ventilasi kipas fan beban load lubrication pelumas",
    "current_a": "arus current beban overload lilitan winding tegangan voltage kabel belt seal",
}


def _pct(f: FeatureStat) -> float | None:
    if f.now is None or not f.normal:
        return None
    return (f.now - f.normal) / abs(f.normal) * 100


def _elevated(f: FeatureStat) -> bool:
    p = _pct(f)
    return (f.z is not None and abs(f.z) >= 2.0) or (p is not None and abs(p) >= 15)


def build_query(body: ExplainIn) -> str:
    """Ubah pola sensor menjadi kata kunci (dwibahasa) agar BM25 menemukan bagian manual yang relevan."""
    terms = ["troubleshooting causes inspection penyebab perbaikan"]
    for key, f in body.features.items():
        if key in _TERMS and _elevated(f):
            terms.append(_TERMS[key])
    for ev in body.recent_events[:3]:
        if ev.transcript:
            terms.append(ev.transcript)
    return " ".join(terms)


def _describe(body: ExplainIn) -> str:
    lines = [
        f"Machine: {body.machine_name or body.machine_id} ({body.machine_id})",
        f"Time: {body.ts or '-'}",
        f"Anomaly score: {body.score:.2f} (0-1, higher = more abnormal)",
        "Sensors (now vs normal):",
    ]
    for key, f in body.features.items():
        name, unit = _SENSOR.get(key, (key, ""))
        p = _pct(f)
        z = f"z={f.z:.1f}" if f.z is not None else "z=n/a"
        if f.now is None:
            lines.append(f"- {name}: no data")
            continue
        change = f"{p:+.0f}% vs normal {f.normal:g}" if p is not None else "normal value unknown"
        flag = " <-- deviating" if _elevated(f) else ""
        lines.append(f"- {name}: {f.now:g} {unit} ({change}, {z}){flag}")
    if body.recent_events:
        lines.append("Recent downtime events:")
        for ev in body.recent_events[:5]:
            lines.append(f"- {ev.ts or '-'} | {ev.category or '-'} | {ev.transcript or '-'}")
    return "\n".join(lines)


def _title(source: str, kind: str) -> str:
    if kind == "riwayat":
        return "Repair history"
    stem = re.sub(r"\.pdf$", "", source, flags=re.I)
    return re.sub(r"[_\-]+", " ", stem).strip() or source


class Explainer:
    def __init__(self, client: TokenFactoryClient, index: RagIndex, settings: Settings):
        self.client, self.index, self.s = client, index, settings

    def retrieve(self, body: ExplainIn) -> list[tuple[str, SourceRef]]:
        q = build_query(body)
        hits = self.index.search(q, k=self.s.rag_top_k, kind="manual") + self.index.search(q, k=2, kind="riwayat")
        out = []
        for n, (chunk, _score) in enumerate(hits, 1):
            snippet = " ".join(chunk.text.split())[:500]
            out.append(
                (
                    f"S{n}",
                    SourceRef(
                        title=_title(chunk.source, chunk.kind),
                        page=chunk.page if chunk.kind == "manual" else None,
                        snippet=snippet,
                    ),
                )
            )
        return out

    async def explain(self, body: ExplainIn) -> ExplainOut:
        started = time.monotonic()
        refs = self.retrieve(body)
        src_block = (
            "\n\n".join(
                f"[{sid}] ({r.title}{', p. ' + str(r.page) if r.page else ''})\n{r.snippet}" for sid, r in refs
            )
            or "(no matching sources)"
        )
        user = f"ALERT:\n{_describe(body)}\n\nSOURCES:\n{src_block}"

        res = await self.client.chat(
            [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
            max_tokens=2500,
            reasoning_effort="low",
            json_mode=True,
            temperature=0.2,
            budget=self.s.explain_budget,
        )
        obj = extract_json(res.content)
        if not obj or not str(obj.get("summary", "")).strip():
            raise UpstreamError(502, f"keluaran model bukan JSON penjelasan: {res.content[:120]!r}")

        used = {str(x).strip("[] ").upper() for x in (obj.get("sources_used") or []) if x}
        cited = [r for sid, r in refs if sid in used]
        urgency = str(obj.get("urgency", "")).strip().lower()
        if urgency not in URGENCY_LEVELS:
            urgency = "inspect within 24h"
        actions = [str(a) for a in (obj.get("actions") or []) if str(a).strip()][:4]

        return ExplainOut(
            summary=str(obj["summary"]).strip(),
            actions=actions,
            urgency=urgency,
            sources=cited,
            grounded=bool(cited),
            usage=make_usage(self.s, self.s.analysis_model, started, res.usage),
        )
