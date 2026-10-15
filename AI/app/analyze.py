"""POST /analyze-downtime (ekstra, belum dipanggil backend) - ringkasan Availability + Pareto, bahasa Inggris."""
import json
import logging
import time

from .config import Settings
from .llm import TokenFactoryClient, UpstreamError, extract_json, make_usage
from .schemas import AnalyzeIn, AnalyzeOut

log = logging.getLogger("ai.analyze")

SYSTEM_PROMPT = """You are a plant productivity analyst. From the Availability and downtime Pareto data,
write a short analysis for a supervisor in plain English.
Use ONLY the numbers provided; never invent numbers. If data is sparse, say it is limited.
The category "Perlu dicek" (Needs review) means the operator's answer had low confidence and needs human verification.
Reply with ONLY valid JSON:
{"summary": "2-3 sentences", "top_findings": ["..."], "recommendations": ["..."]}
At most 4 findings and 4 recommendations, one sentence each."""


def _rule_summary(body: AnalyzeIn) -> AnalyzeOut:
    items = sorted(body.pareto, key=lambda p: p.minutes, reverse=True)
    total = sum(p.minutes for p in items) or 1
    findings = [f"{p.category}: {p.minutes:.0f} min ({p.minutes / total:.0%} of downtime)" for p in items[:3]]
    av = f"Availability {body.availability_pct:.1f}%. " if body.availability_pct is not None else ""
    return AnalyzeOut(
        summary=f"{av}Total downtime {total:.0f} min ({body.period}). AI analysis unavailable; figures computed directly from the data.",
        top_findings=findings,
        recommendations=[],
    )


async def analyze(client: TokenFactoryClient, settings: Settings, body: AnalyzeIn) -> AnalyzeOut:
    if not body.pareto:
        return AnalyzeOut(summary="No downtime data for this period yet.", top_findings=[], recommendations=[])
    started = time.monotonic()
    try:
        res = await client.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(body.model_dump(exclude_none=True), ensure_ascii=False)},
            ],
            max_tokens=2000,
            reasoning_effort="low",
            json_mode=True,
            budget=45,
        )
        obj = extract_json(res.content)
        if not obj or "summary" not in obj:
            raise ValueError("keluaran bukan JSON valid")
        return AnalyzeOut(
            summary=str(obj["summary"]),
            top_findings=[str(x) for x in obj.get("top_findings", [])][:4],
            recommendations=[str(x) for x in obj.get("recommendations", [])][:4],
            usage=make_usage(settings, settings.analysis_model, started, res.usage),
        )
    except (UpstreamError, ValueError) as e:
        log.warning("analyze gagal: %s", e)
        return _rule_summary(body)
