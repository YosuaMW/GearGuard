import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.classify import Classifier
from app.config import Settings
from app.explain import Explainer, build_query
from app.llm import ChatResult, RateLimiter, UpstreamError, extract_json
from app.main import app
from app.rag import RagIndex, chunk_text
from app.schemas import CATEGORIES, ClassifyIn, ExplainIn

S = Settings(radeon_api_key="x")

# Payload persis dari docs/role3-ai.md bagian 3
DOC_EXPLAIN = {
    "alert_id": 4,
    "machine_id": "m2",
    "machine_name": "Pump",
    "ts": "2026-10-14T09:24:25Z",
    "score": 0.80,
    "features": {
        "vib_rms": {"now": 0.55, "normal": 0.40, "z": 4.75},
        "temp_c": {"now": 46.6, "normal": 45.3, "z": 2.09},
        "current_a": {"now": 2.33, "normal": 2.30, "z": 1.03},
    },
    "recent_events": [
        {"ts": "2026-10-14T09:10:12Z", "category": "Breakdown – Mekanik", "transcript": "seal pompa bocor, diganti dulu"}
    ],
}


class FakeClient:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    async def chat(self, messages, **kw):
        self.calls.append((messages, kw))
        if self.error:
            raise self.error
        body = self.reply if isinstance(self.reply, str) else json.dumps(self.reply)
        return ChatResult(content=body, usage={"prompt_tokens": 100, "completion_tokens": 20})


def run(c):
    return asyncio.run(c)


def test_extract_json_variants():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Berikut: {"a": 2} selesai') == {"a": 2}
    assert extract_json("bukan json") is None


def test_classify_contract_and_prompt_rules():
    fc = FakeClient({"category": "Breakdown – Overheat", "confidence": 0.9, "rationale": "motor panas"})
    out = run(Classifier(fc, S).classify(ClassifyIn(text="motor panas, nunggu teknisi", machine_id="m1")))
    assert out.category == "Breakdown – Overheat" and out.confidence == 0.9
    assert out.usage.model == "Qwen3.8-27B" and out.usage.prompt_tokens == 100 and out.usage.gpu
    msgs, kw = fc.calls[0]
    # Qwen3.8-27B: tepat satu system message di indeks 0; reasoning_effort bukan 'high'
    assert [m["role"] for m in msgs] == ["system", "user"] and kw["reasoning_effort"] in ("low", "medium", "xhigh")


@pytest.mark.parametrize("raw,expected", [("Breakdown - Listrik", "Breakdown – Listrik"), ("istirahat/terjadwal", "Istirahat/terjadwal")])
def test_classify_normalizes_hyphen_and_case(raw, expected):
    out = run(Classifier(FakeClient({"category": raw, "confidence": 0.8}), S).classify(ClassifyIn(text="x")))
    assert out.category == expected and out.category in CATEGORIES


def test_classify_unknown_category_becomes_lainnya_low_confidence():
    out = run(Classifier(FakeClient({"category": "Kategori Ngawur", "confidence": 0.95}), S).classify(ClassifyIn(text="entahlah")))
    assert out.category == "Lainnya" and out.confidence <= 0.3


def test_classify_failure_raises_so_backend_uses_its_fallback():
    with pytest.raises(UpstreamError):
        run(Classifier(FakeClient(error=UpstreamError(429, "limit")), S).classify(ClassifyIn(text="x")))
    with pytest.raises(UpstreamError):
        run(Classifier(FakeClient("bukan json sama sekali"), S).classify(ClassifyIn(text="x")))


def test_rag_search_and_persistence(tmp_path):
    idx = RagIndex(str(tmp_path))
    idx.add_document("manual.pdf", "manual", [(3, "Getaran berlebih pada motor disebabkan bearing aus atau poros tidak lurus."), (4, "Prosedur penyimpanan kabel dan label.")])
    hits = idx.search("getaran bearing motor", k=2)
    assert hits and hits[0][0].page == 3
    assert RagIndex(str(tmp_path)).stats()["chunks"] == idx.stats()["chunks"]
    assert len(chunk_text("kata " * 1000)) > 1


def test_explain_doc_payload_grounded(tmp_path):
    idx = RagIndex(str(tmp_path))
    idx.add_document("Centrifugal_pump_manual.pdf", "manual", [(42, "Excessive vibration is usually caused by worn bearings, misalignment or loose mounting bolts. Getaran berlebih.")])
    reply = {"summary": "Vibration is 38% above normal [S1].", "actions": ["Check bearing noise", "Inspect mounting bolts"], "urgency": "inspect within 24h", "sources_used": ["S1", "S9"]}
    out = run(Explainer(FakeClient(reply), idx, S).explain(ExplainIn(**DOC_EXPLAIN)))
    assert out.grounded and len(out.sources) == 1
    assert out.sources[0].title == "Centrifugal pump manual" and out.sources[0].page == 42
    assert out.urgency == "inspect within 24h" and out.usage.latency_ms >= 0
    body = ExplainIn(**DOC_EXPLAIN)
    q = build_query(body)
    assert "vibration" in q and "seal" in q  # sensor yang menyimpang + riwayat kejadian ikut jadi kueri


def test_explain_bad_urgency_and_null_features(tmp_path):
    reply = {"summary": "ok", "actions": ["a"], "urgency": "sometime", "sources_used": []}
    payload = {**DOC_EXPLAIN, "features": {"vib_rms": {"now": None, "normal": None, "z": None}}}
    out = run(Explainer(FakeClient(reply), RagIndex(str(tmp_path)), S).explain(ExplainIn(**payload)))
    assert out.urgency == "inspect within 24h" and not out.grounded and out.sources == []


def test_explain_failure_raises_so_backend_keeps_rules(tmp_path):
    with pytest.raises(UpstreamError):
        run(Explainer(FakeClient(error=UpstreamError(503, "down")), RagIndex(str(tmp_path)), S).explain(ExplainIn(**DOC_EXPLAIN)))


def test_rate_limiter_fails_fast_when_budget_too_small():
    async def go():
        rl = RateLimiter(1)
        await rl.acquire()
        await rl.acquire(max_wait=0.5)

    with pytest.raises(UpstreamError) as e:
        run(go())
    assert e.value.status == 429


@pytest.fixture
def api(tmp_path):
    s = Settings(radeon_api_key="x", ai_service_key="rahasia", data_dir=str(tmp_path))
    fc = FakeClient({"category": "Tunggu material", "confidence": 0.8, "rationale": "bahan habis"})
    app.state.settings, app.state.llm = s, fc
    app.state.index = RagIndex(str(tmp_path))
    app.state.classifier = Classifier(fc, s)
    app.state.explainer = Explainer(fc, app.state.index, s)
    return TestClient(app)


def test_http_bearer_auth_and_response_shape(api):
    body = {"text": "material dari gudang belum datang"}
    assert api.post("/classify", json=body).status_code == 401
    assert api.post("/classify", json=body, headers={"Authorization": "Bearer salah"}).status_code == 401
    r = api.post("/classify", json=body, headers={"Authorization": "Bearer rahasia"})
    j = r.json()
    assert r.status_code == 200 and j["category"] == "Tunggu material" and j["usage"]["model"] == "Qwen3.8-27B"
    assert api.get("/health").json()["status"] == "ok"


def test_http_upstream_error_is_non_2xx(api):
    app.state.classifier = Classifier(FakeClient(error=UpstreamError(503, "down")), app.state.settings)
    r = api.post("/classify", json={"text": "x"}, headers={"Authorization": "Bearer rahasia"})
    assert r.status_code == 502
