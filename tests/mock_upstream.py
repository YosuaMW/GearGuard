"""Token Factory palsu untuk uji kontrak (tidak memakai kuota API asli)."""
import json

from fastapi import FastAPI, File, Form, Request, UploadFile

app = FastAPI()


def _reply(obj: dict) -> dict:
    return {
        "choices": [{"message": {"content": json.dumps(obj)}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 10},
    }


@app.post("/v1/chat/completions")
async def chat(req: Request):
    b = await req.json()
    system, user = b["messages"][0]["content"], b["messages"][-1]["content"]
    if "klasifikator" in system:
        text = str(user).lower()
        cat = "Breakdown - Overheat" if "panas" in text else "Tunggu material" if "material" in text else "Lainnya"
        return _reply({"category": cat, "confidence": 0.86, "rationale": "mock"})
    if "maintenance assistant" in system:
        used = ["S1"] if "[S1]" in user else []
        return _reply(
            {"summary": "Vibration is 38% above normal, consistent with early bearing wear [S1].",
             "actions": ["Check bearing noise and temperature", "Inspect mounting bolts"],
             "urgency": "inspect within 24h", "sources_used": used}
        )
    return {"choices": [{"message": {"content": "motor panas nunggu teknisi"}, "finish_reason": "stop"}], "usage": {}}


@app.post("/v1/audio/transcriptions")  # dipakai sebagai Whisper palsu
async def whisper(file: UploadFile = File(...), model: str = Form("")):
    await file.read()
    return {"text": "motor panas, nunggu teknisi"}
