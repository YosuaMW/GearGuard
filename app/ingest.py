"""Ingest PDF manual -> indeks RAG, memakai MinerU2.5-Pro untuk OCR.

Mode `auto` (default): ambil teks bawaan PDF lewat pypdf (gratis, tanpa kuota API);
hanya halaman yang hampir kosong (hasil scan/gambar) dikirim ke MinerU.
Mode `always`: semua halaman lewat MinerU (kualitas tabel/rumus terbaik, memakai kuota).
Mode `never`: hanya pypdf.
"""
import io
import logging

from pypdf import PdfReader

from .config import Settings
from .llm import TokenFactoryClient, UpstreamError
from .rag import RagIndex

log = logging.getLogger("ai.ingest")
MIN_TEXT_CHARS = 60


def _ranges(pages: list[int], batch: int) -> list[tuple[int, int]]:
    """Kelompokkan nomor halaman (0-based) menjadi rentang berurutan maks `batch` halaman."""
    out: list[tuple[int, int]] = []
    for p in sorted(pages):
        if out and p == out[-1][1] + 1 and out[-1][1] - out[-1][0] + 1 < batch:
            out[-1] = (out[-1][0], p)
        else:
            out.append((p, p))
    return out


async def ocr_pdf_pages(client: TokenFactoryClient, data: bytes, page_numbers: list[int], batch: int) -> dict[int, str]:
    """OCR halaman tertentu (0-based). Mengembalikan {nomor_halaman: markdown}."""
    result: dict[int, str] = {}
    for a, b in _ranges(page_numbers, batch):
        spec = f"{a}-{b}" if b > a else f"{a}"
        md_pages = await client.ocr(data, "application/pdf", pages=spec)
        for offset, md in enumerate(md_pages):
            result[a + offset] = md
    return result


async def ingest_pdf(
    client: TokenFactoryClient, index: RagIndex, settings: Settings, filename: str, data: bytes, kind: str = "manual"
) -> dict:
    reader = PdfReader(io.BytesIO(data))
    total = len(reader.pages)
    texts: dict[int, str] = {}
    for i, page in enumerate(reader.pages):
        try:
            texts[i] = (page.extract_text() or "").strip()
        except Exception:  # pypdf bisa gagal pada PDF aneh
            texts[i] = ""

    mode = settings.ocr_mode.lower()
    if mode == "always":
        need = list(range(total))
    elif mode == "never":
        need = []
    else:
        need = [i for i, t in texts.items() if len(t) < MIN_TEXT_CHARS]

    ocr_done = 0
    if need:
        try:
            ocr_text = await ocr_pdf_pages(client, data, need, settings.ocr_batch_pages)
            for i, md in ocr_text.items():
                if md.strip():
                    texts[i] = md.strip()
                    ocr_done += 1
        except UpstreamError as e:
            if mode == "always" and not any(texts.values()):
                raise
            log.warning("OCR gagal (%s); lanjut dengan teks bawaan PDF", e)

    pages = [(i + 1, t) for i, t in sorted(texts.items()) if t]
    if not pages:
        raise ValueError("Tidak ada teks yang bisa diekstrak dari PDF (coba OCR_MODE=always)")
    chunks = index.add_document(filename, kind, pages)
    return {"source": filename, "kind": kind, "pages": total, "chunks_added": chunks, "ocr_pages": ocr_done}
