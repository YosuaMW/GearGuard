"""Skema sesuai docs/role3-ai.md di repo SiagaMesin (kontrak dengan backend Raspberry Pi)."""
from pydantic import BaseModel, Field

# Nilai persis yang disimpan backend di database (pemisah = en dash "–", bukan "-")
CATEGORIES = [
    "Breakdown – Mekanik",
    "Breakdown – Listrik",
    "Breakdown – Overheat",
    "Ganti produk/setup",
    "Tunggu material",
    "Istirahat/terjadwal",
    "Lainnya",
]

URGENCY_LEVELS = ["monitor", "inspect within 24h", "inspect within 4h", "inspect now"]


class Usage(BaseModel):
    """Dicatat backend ke tabel ai_calls -> halaman 'Running on AMD'."""

    model: str
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    gpu: str | None = None


# ---------- POST /transcribe ----------
class TranscribeOut(BaseModel):
    text: str
    language: str = "id"
    backend: str
    usage: Usage


# ---------- POST /classify ----------
class ClassifyIn(BaseModel):
    text: str = Field(..., min_length=1)
    machine_id: str | None = None
    context: dict | None = None  # opsional, tidak dikirim backend saat ini


class ClassifyOut(BaseModel):
    category: str
    confidence: float = Field(..., ge=0, le=1)
    rationale: str = ""
    usage: Usage


# ---------- POST /explain ----------
class FeatureStat(BaseModel):
    now: float | None = None  # alert lama bisa null
    normal: float | None = None
    z: float | None = None


class RecentEvent(BaseModel):
    ts: str | None = None
    category: str | None = None
    transcript: str | None = None


class ExplainIn(BaseModel):
    alert_id: int | None = None
    machine_id: str
    machine_name: str | None = None
    ts: str | None = None
    score: float
    features: dict[str, FeatureStat] = {}  # kunci: vib_rms | temp_c | current_a
    recent_events: list[RecentEvent] = []


class SourceRef(BaseModel):
    title: str
    page: int | None = None
    snippet: str


class ExplainOut(BaseModel):
    summary: str
    actions: list[str]
    urgency: str
    sources: list[SourceRef]
    grounded: bool = Field(..., description="False bila tidak ada sumber manual/riwayat yang dikutip")
    usage: Usage


# ---------- Ekstra (belum dipakai backend): POST /analyze-downtime ----------
class ParetoItem(BaseModel):
    category: str
    minutes: float
    count: int = 0


class AnalyzeIn(BaseModel):
    period: str = "this shift"
    machine_id: str | None = None
    availability_pct: float | None = None
    pareto: list[ParetoItem]
    needs_review_count: int = 0
    alerts_count: int = 0
    notes: str | None = None


class AnalyzeOut(BaseModel):
    summary: str
    top_findings: list[str]
    recommendations: list[str]
    usage: Usage | None = None


# ---------- OCR / RAG ----------
class OcrOut(BaseModel):
    filename: str
    pages: list[str]
    pages_count: int


class IngestOut(BaseModel):
    source: str
    kind: str
    pages: int
    chunks_added: int
    ocr_pages: int


class RepairRecord(BaseModel):
    machine_id: str | None = None
    date: str | None = None
    symptom: str
    cause: str
    action: str
