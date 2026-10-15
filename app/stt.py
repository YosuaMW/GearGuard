"""POST /transcribe - voice note (.ogg Opus dari Telegram) -> teks bahasa Indonesia.

Token Factory TIDAK menyediakan endpoint audio/transcriptions. Dua backend:
1. Whisper di instance GPU AMD (vLLM, OpenAI-compatible)  -> set WHISPER_BASE_URL (sesuai rencana jobdesk)
2. Fallback: MiMo-V2.6-Flash lewat Token Factory (satu-satunya model yang menerima audio) -> butuh ffmpeg
"""
import asyncio
import base64
import logging
import time

import httpx

from .config import Settings
from .llm import TokenFactoryClient, UpstreamError, make_usage
from .schemas import TranscribeOut

log = logging.getLogger("ai.stt")

_TRANSCRIBE_PROMPT = (
    "Transkripsikan audio berikut persis seperti diucapkan dalam bahasa Indonesia. "
    "Balas hanya dengan teks transkrip, tanpa komentar, tanpa terjemahan."
)


async def _to_wav(data: bytes) -> bytes:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
            "-ac", "1", "-ar", "16000", "-f", "wav", "pipe:1",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        raise UpstreamError(500, "ffmpeg tidak terpasang di server AI")
    out, err = await proc.communicate(data)
    if proc.returncode != 0 or not out:
        raise UpstreamError(415, f"ffmpeg gagal mengonversi audio: {err.decode(errors='ignore')[:200]}")
    return out


class Transcriber:
    def __init__(self, client: TokenFactoryClient, settings: Settings):
        self.client, self.s = client, settings
        self.http = httpx.AsyncClient(timeout=settings.transcribe_budget)

    async def aclose(self) -> None:
        await self.http.aclose()

    async def transcribe(self, data: bytes, filename: str = "voice.ogg", content_type: str = "audio/ogg") -> TranscribeOut:
        started = time.monotonic()
        if self.s.whisper_base_url:
            try:
                return await self._whisper(data, filename, content_type, started)
            except (httpx.HTTPError, UpstreamError) as e:
                log.warning("Whisper AMD gagal (%r), coba fallback MiMo", e)
        return await self._mimo(data, started)

    async def _whisper(self, data: bytes, filename: str, content_type: str, started: float) -> TranscribeOut:
        url = self.s.whisper_base_url.rstrip("/") + "/audio/transcriptions"
        resp = await self.http.post(
            url,
            headers={"Authorization": f"Bearer {self.s.whisper_api_key}"},
            files={"file": (filename, data, content_type)},
            data={"model": self.s.whisper_model, "language": "id", "response_format": "json", "temperature": "0"},
        )
        if resp.status_code >= 400:
            raise UpstreamError(resp.status_code, resp.text[:200])
        text = (resp.json().get("text") or "").strip()
        return TranscribeOut(
            text=text, language="id", backend="whisper-amd",
            usage=make_usage(self.s, self.s.whisper_model.split("/")[-1], started),
        )

    async def _mimo(self, data: bytes, started: float) -> TranscribeOut:
        wav = await _to_wav(data)
        remaining = max(self.s.transcribe_budget - (time.monotonic() - started), 3.0)
        res = await self.client.chat(
            [
                {"role": "system", "content": "Kamu mesin transkripsi audio bahasa Indonesia."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _TRANSCRIBE_PROMPT},
                        {"type": "input_audio", "input_audio": {"data": base64.b64encode(wav).decode(), "format": "wav"}},
                    ],
                },
            ],
            model=self.s.audio_model,
            max_tokens=1024,
            reasoning_effort="none",  # MiMo: none mematikan thinking -> lebih cepat (< 10 dtk)
            temperature=0.0,
            budget=remaining,
        )
        return TranscribeOut(
            text=res.content.strip(), language="id", backend=f"token-factory:{self.s.audio_model}",
            usage=make_usage(self.s, self.s.audio_model, started, res.usage),
        )
