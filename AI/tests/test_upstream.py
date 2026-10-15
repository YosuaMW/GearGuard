import asyncio
import io

import httpx
from pypdf import PdfWriter

from app.config import Settings
from app.ingest import _ranges, ingest_pdf
from app.llm import TokenFactoryClient
from app.rag import RagIndex


def make_client(handler, **kw):
    s = Settings(radeon_api_key="rc-test", rpm_limit=1000, **kw)
    c = TokenFactoryClient(s)
    c.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return c


def test_retry_on_429_then_success(monkeypatch):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": {"message": "rate"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})

    async def go():
        c = make_client(handler)
        return await c.chat([{"role": "user", "content": "hai"}])

    assert asyncio.run(go()).content == "ok" and calls["n"] == 2


def test_empty_content_length_retries_with_more_tokens():
    seen = []

    def handler(req):
        import json

        body = json.loads(req.content)
        seen.append(body["max_tokens"])
        if len(seen) == 1:
            return httpx.Response(200, json={"choices": [{"message": {"content": ""}, "finish_reason": "length"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]})

    async def go():
        return await make_client(handler).chat([{"role": "user", "content": "x"}], max_tokens=500)

    assert asyncio.run(go()).content == "{}" and seen == [500, 1000]


def test_ranges_batching():
    assert _ranges([0, 1, 2, 3, 4, 5, 9], 3) == [(0, 2), (3, 5), (9, 9)]


def test_ingest_blank_pdf_uses_ocr_for_scanned_pages(tmp_path):
    w = PdfWriter()
    for _ in range(3):
        w.add_blank_page(200, 200)
    buf = io.BytesIO()
    w.write(buf)
    specs = []

    def handler(req):
        import json

        body = json.loads(req.content)
        specs.append(body["pages"])
        return httpx.Response(200, json={"pages": [{"markdown": f"# Halaman {i}\nGetaran motor dan bearing"} for i in range(3)]})

    async def go():
        c = make_client(handler)
        idx = RagIndex(str(tmp_path))
        info = await ingest_pdf(c, idx, c.s, "scan.pdf", buf.getvalue())
        return info, idx

    info, idx = asyncio.run(go())
    assert specs == ["0-2"] and info["ocr_pages"] == 3 and idx.search("getaran bearing")
