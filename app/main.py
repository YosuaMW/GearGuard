import asyncio
import hmac
import json
import logging
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .analyze import analyze
from .classify import Classifier
from .config import Settings, get_settings
from .explain import Explainer
from .ingest import ingest_pdf
from .llm import TokenFactoryClient, UpstreamError
from .rag import RagIndex, load_repair_history, sync_repair_history
from .schemas import (
    CATEGORIES,
    AnalyzeIn,
    AnalyzeOut,
    ClassifyIn,
    ClassifyOut,
    ExplainIn,
    ExplainOut,
    IngestOut,
    OcrOut,
    RepairRecord,
    TranscribeOut,
)
from .stt import Transcriber

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ai.main")

MAX_AUDIO_BYTES = 25 * 1024 * 1024
MAX_DOC_BYTES = 60 * 1024 * 1024


async def _ingest_missing_manuals(app: FastAPI) -> None:
    s: Settings = app.state.settings
    folder = Path(s.manuals_dir)
    folder.mkdir(parents=True, exist_ok=True)
    known = set(app.state.index.stats()["sources"])
    for pdf in sorted(folder.glob("*.pdf")):
        if pdf.name in known:
            continue
        try:
            info = await ingest_pdf(app.state.llm, app.state.index, s, pdf.name, pdf.read_bytes())
            log.info("manual di-ingest: %s", info)
        except Exception as e:  # satu PDF bermasalah tidak boleh menghentikan layanan
            log.error("ingest %s gagal: %s", pdf.name, e)


def _seed_repair_history(s: Settings) -> None:
    target, seed = Path(s.repair_history_file), Path(s.repair_history_seed)
    if not target.exists() and seed.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(seed, target)
        log.info("riwayat perbaikan contoh disalin dari %s (ganti dengan data nyata!)", seed)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if not s.ai_service_key:
        log.warning("AI_SERVICE_KEY kosong: endpoint TIDAK terautentikasi (hanya untuk uji lokal)")
    if not s.radeon_api_key:
        log.warning("RADEON_API_KEY kosong: semua panggilan model akan gagal")
    app.state.settings = s
    app.state.llm = TokenFactoryClient(s)
    app.state.index = RagIndex(s.data_dir)
    app.state.classifier = Classifier(app.state.llm, s)
    app.state.explainer = Explainer(app.state.llm, app.state.index, s)
    app.state.stt = Transcriber(app.state.llm, s)
    _seed_repair_history(s)
    sync_repair_history(app.state.index, s.repair_history_file)
    task = asyncio.create_task(_ingest_missing_manuals(app))  # tidak memblokir startup
    yield
    task.cancel()
    await app.state.stt.aclose()
    await app.state.llm.aclose()


app = FastAPI(title="SiagaMesin AI Service", version="1.1.0", lifespan=lifespan)
# Backend memanggil server-ke-server; CORS hanya untuk uji lewat /docs di browser
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(UpstreamError)
async def upstream_handler(_: Request, exc: UpstreamError):
    # Selalu non-2xx agar backend mencatat ok=False dan memakai fallback-nya
    status = exc.status if exc.status in (400, 401, 403, 415, 429) else 502
    return JSONResponse(status_code=status, content={"error": "upstream_error", "upstream_status": exc.status, "detail": exc.detail})


# HTTPBearer membuat tombol "Authorize" di Swagger /docs. Kolom header bernama "Authorization" biasa
# DIABAIKAN oleh Swagger UI (aturan OpenAPI), jadi kunci tidak pernah terkirim lewat kolom itu.
bearer = HTTPBearer(auto_error=False, description="Isi HANYA kuncinya (nilai AI_SERVICE_KEY). Kata 'Bearer' ditambahkan otomatis.")


async def auth(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    expected = request.app.state.settings.ai_service_key
    if not expected:
        return
    # Pesan dibedakan agar mudah di-debug; tidak ada isi kunci yang dibocorkan di respons
    if creds is None:
        raise HTTPException(401, "Header 'Authorization: Bearer <AI_SERVICE_KEY>' tidak terkirim atau formatnya salah. Di Swagger: klik tombol Authorize.")
    token = creds.credentials.strip()
    if not hmac.compare_digest(token, expected):
        log.warning("auth gagal: panjang kunci kiriman=%d, panjang AI_SERVICE_KEY di server=%d", len(token), len(expected))
        raise HTTPException(401, "Kunci tidak cocok dengan AI_SERVICE_KEY di server (cek terminal uvicorn)")


Protected = [Depends(auth)]


async def _read(file: UploadFile, limit: int) -> bytes:
    data = await file.read()
    if not data:
        raise HTTPException(400, "File kosong")
    if len(data) > limit:
        raise HTTPException(413, f"File lebih dari {limit // 1024 // 1024} MB")
    return data


# ---------------------------------------------------------------- health
@app.get("/health")
async def health(request: Request):
    s: Settings = request.app.state.settings
    return {
        "status": "ok",
        "models": {"analysis": s.analysis_model, "ocr": s.ocr_model},
        "stt_backend": "whisper-amd" if s.whisper_base_url else f"token-factory:{s.audio_model}",
        "token_factory_key_configured": bool(s.radeon_api_key),
        "auth_enabled": bool(s.ai_service_key),
        "rag": request.app.state.index.stats(),
        "categories": CATEGORIES,
    }


# ---------------------------------------------------------------- kontrak dengan backend (docs/role3-ai.md)
@app.post("/transcribe", response_model=TranscribeOut, dependencies=Protected)
async def transcribe(request: Request, file: UploadFile = File(...)):
    data = await _read(file, MAX_AUDIO_BYTES)
    return await request.app.state.stt.transcribe(data, file.filename or "voice.ogg", file.content_type or "audio/ogg")


@app.post("/classify", response_model=ClassifyOut, dependencies=Protected)
async def classify(request: Request, body: ClassifyIn):
    return await request.app.state.classifier.classify(body)


@app.post("/explain", response_model=ExplainOut, dependencies=Protected)
async def explain(request: Request, body: ExplainIn):
    return await request.app.state.explainer.explain(body)


# ---------------------------------------------------------------- ekstra (belum dipanggil backend)
@app.post("/analyze-downtime", response_model=AnalyzeOut, dependencies=Protected)
async def analyze_downtime(request: Request, body: AnalyzeIn):
    return await analyze(request.app.state.llm, request.app.state.settings, body)


# ---------------------------------------------------------------- OCR & basis pengetahuan (MinerU2.5-Pro)
@app.post("/ocr", response_model=OcrOut, dependencies=Protected)
async def ocr(request: Request, file: UploadFile = File(...), pages: str | None = None):
    """OCR PDF/gambar -> markdown per halaman. `pages` contoh "0-2" (nomor halaman mulai 0)."""
    data = await _read(file, MAX_DOC_BYTES)
    mime = file.content_type or ("application/pdf" if (file.filename or "").lower().endswith(".pdf") else "image/png")
    md = await request.app.state.llm.ocr(data, mime, pages=pages)
    return OcrOut(filename=file.filename or "document", pages=md, pages_count=len(md))


@app.post("/rag/ingest", response_model=IngestOut, dependencies=Protected)
async def rag_ingest(request: Request, file: UploadFile = File(...)):
    """Unggah PDF manual -> OCR (MinerU) bila perlu -> indeks RAG. File juga disimpan ke folder manuals."""
    name = Path(file.filename or "manual.pdf").name
    if not name.lower().endswith(".pdf"):
        raise HTTPException(400, "Hanya file PDF")
    data = await _read(file, MAX_DOC_BYTES)
    s: Settings = request.app.state.settings
    try:
        info = await ingest_pdf(request.app.state.llm, request.app.state.index, s, name, data)
    except ValueError as e:
        raise HTTPException(422, str(e))
    Path(s.manuals_dir).mkdir(parents=True, exist_ok=True)
    (Path(s.manuals_dir) / name).write_bytes(data)
    return info


@app.get("/rag/status", dependencies=Protected)
async def rag_status(request: Request):
    return request.app.state.index.stats()


@app.post("/rag/repair-history", dependencies=Protected)
async def add_repair(request: Request, rec: RepairRecord):
    """Tambah satu riwayat perbaikan (dari teknisi) lalu sinkron ke indeks."""
    s: Settings = request.app.state.settings
    records = load_repair_history(s.repair_history_file)
    records.append(rec.model_dump(exclude_none=True))
    p = Path(s.repair_history_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"records": len(records), "chunks": sync_repair_history(request.app.state.index, s.repair_history_file)}