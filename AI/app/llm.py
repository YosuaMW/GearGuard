import asyncio
import base64
import json
import logging
import random
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import Settings

log = logging.getLogger("ai.llm")


class UpstreamError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(f"upstream {status}: {detail}")
        self.status = status
        self.detail = detail


@dataclass
class ChatResult:
    content: str
    reasoning: str = ""
    finish_reason: str = ""
    usage: dict = field(default_factory=dict)


class RateLimiter:
    """Sliding window 60 detik."""

    def __init__(self, rpm: int):
        self.rpm = max(1, rpm)
        self._ts: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self, max_wait: float | None = None) -> None:
        """Tunggu slot RPM. Bila antrean lebih lama dari `max_wait` detik -> gagal cepat (429)."""
        waited = 0.0
        while True:
            async with self._lock:
                now = time.monotonic()
                while self._ts and now - self._ts[0] >= 60:
                    self._ts.popleft()
                if len(self._ts) < self.rpm:
                    self._ts.append(now)
                    return
                wait = 60 - (now - self._ts[0])
            if max_wait is not None and waited + wait > max_wait:
                raise UpstreamError(429, "kuota RPM lokal penuh, antrean melebihi batas waktu")
            step = max(min(wait, 1.0), 0.05)
            await asyncio.sleep(step)
            waited += step


def make_usage(settings: Settings, model: str, started: float, usage: dict | None = None) -> dict:
    """Field `usage` yang diminta backend untuk halaman 'Running on AMD' (docs/role3-ai.md bagian 4)."""
    u = usage or {}
    return {
        "model": model,
        "latency_ms": int((time.monotonic() - started) * 1000),
        "prompt_tokens": u.get("prompt_tokens"),
        "completion_tokens": u.get("completion_tokens"),
        "gpu": settings.gpu_label,
    }


def extract_json(text: str) -> dict | None:
    """Ambil objek JSON dari teks model (toleran terhadap code fence / teks tambahan)."""
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _error_message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except Exception:
        return resp.text[:300]
    # Gateway: {"error":{...}}  |  Platform: {"detail":{"error":{...}}}
    err = body.get("error") or (body.get("detail") or {}).get("error") or body.get("detail") or body
    if isinstance(err, dict):
        return str(err.get("message") or err)[:300]
    return str(err)[:300]


class TokenFactoryClient:
    def __init__(self, settings: Settings):
        self.s = settings
        self.limiter = RateLimiter(settings.rpm_limit)
        self.sem = asyncio.Semaphore(settings.max_concurrency)
        self.http = httpx.AsyncClient(timeout=settings.request_timeout)
        self.base = settings.radeon_base_url.rstrip("/")

    async def aclose(self) -> None:
        await self.http.aclose()

    def _headers(self) -> dict:
        if not self.s.radeon_api_key:
            raise UpstreamError(401, "RADEON_API_KEY belum diisi")
        return {"Authorization": f"Bearer {self.s.radeon_api_key}"}

    async def _post(self, path: str, payload: dict, timeout: float | None = None, budget: float | None = None) -> dict:
        """`budget` = batas total detik (backend punya timeout sendiri: 20 dtk classify, 30 dtk transcribe)."""
        url = f"{self.base}{path}"
        last: UpstreamError | None = None
        deadline = time.monotonic() + budget if budget else None

        def remaining() -> float | None:
            return None if deadline is None else deadline - time.monotonic()

        for attempt in range(self.s.max_retries + 1):
            rem = remaining()
            if rem is not None and rem <= 0:
                raise last or UpstreamError(504, "melewati batas waktu")
            await self.limiter.acquire(max_wait=rem)
            rem = remaining()
            if rem is not None and rem <= 0:
                raise last or UpstreamError(504, "melewati batas waktu")
            req_timeout = timeout or self.s.request_timeout
            if rem is not None:
                req_timeout = min(req_timeout, rem)
            try:
                async with self.sem:
                    resp = await self.http.post(url, json=payload, headers=self._headers(), timeout=req_timeout)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last = UpstreamError(503, f"koneksi gagal: {e!r}")
                await asyncio.sleep(min(2**attempt + random.random(), 20))
                continue

            if resp.status_code < 400:
                return resp.json()

            last = UpstreamError(resp.status_code, _error_message(resp))
            if resp.status_code in (429, 502, 503) and attempt < self.s.max_retries:
                retry_after = resp.headers.get("Retry-After")
                try:
                    wait = float(retry_after) if retry_after else 2**attempt
                except ValueError:
                    wait = 2**attempt
                wait = min(wait + random.random(), 65)
                rem = remaining()
                if rem is not None and wait >= rem:
                    raise last  # menunggu tidak akan sempat; biarkan backend memakai fallback-nya
                log.warning("upstream %s, retry dalam %.1fs (percobaan %d)", resp.status_code, wait, attempt + 1)
                await asyncio.sleep(wait)
                continue
            raise last
        raise last or UpstreamError(503, "gagal tanpa detail")

    async def chat(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        max_tokens: int = 2048,
        reasoning_effort: str | None = "low",
        json_mode: bool = False,
        temperature: float = 0.2,
        budget: float | None = None,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": model or self.s.analysis_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        started = time.monotonic()
        data = await self._post("/chat/completions", payload, budget=budget)
        res = self._parse_chat(data)
        if not res.content.strip() and res.finish_reason == "length":
            payload["max_tokens"] = min(max_tokens * 2, 8192)
            left = None if not budget else max(budget - (time.monotonic() - started), 1.0)
            res2 = self._parse_chat(await self._post("/chat/completions", payload, budget=left))
            # jumlahkan pemakaian token kedua panggilan agar halaman usage jujur
            for k in ("prompt_tokens", "completion_tokens"):
                if res.usage.get(k) is not None and res2.usage.get(k) is not None:
                    res2.usage[k] = res.usage[k] + res2.usage[k]
            res = res2
        return res

    @staticmethod
    def _parse_chat(data: dict) -> ChatResult:
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        return ChatResult(
            content=msg.get("content") or "",
            reasoning=msg.get("reasoning") or "",
            finish_reason=choice.get("finish_reason") or "",
            usage=data.get("usage") or {},
        )

    async def ocr(self, document: bytes | str, mime: str = "application/pdf", pages: str | None = None) -> list[str]:
        """MinerU2.5-Pro lewat POST /v1/ocr. Mengembalikan markdown per halaman.

        `document` boleh URL (str) atau bytes (dikirim sebagai data URL).
        """
        if isinstance(document, bytes):
            doc_url = f"data:{mime};base64,{base64.b64encode(document).decode()}"
        else:
            doc_url = document
        payload: dict[str, Any] = {
            "model": self.s.ocr_model,
            "document": {"type": "document_url", "document_url": doc_url},
        }
        if pages:
            payload["pages"] = pages
        data = await self._post("/ocr", payload, timeout=self.s.ocr_timeout)
        return [(p.get("markdown") or "") for p in data.get("pages", [])]

    async def models(self) -> list[str]:
        await self.limiter.acquire()
        resp = await self.http.get(f"{self.base}/models", headers=self._headers())
        if resp.status_code >= 400:
            raise UpstreamError(resp.status_code, _error_message(resp))
        body = resp.json()
        items = body.get("data", body if isinstance(body, list) else [])
        return [m.get("id") or m.get("name") for m in items if isinstance(m, dict)]
