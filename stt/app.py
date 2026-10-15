import os, subprocess
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException
from faster_whisper import WhisperModel

MODEL = os.getenv("STT_MODEL", "base")
KEY = os.getenv("STT_API_KEY", "")
model = WhisperModel(MODEL, device="cpu", compute_type="int8", cpu_threads=4)
app = FastAPI()

def load_audio(data):
    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", "pipe:0",
         "-f", "s16le", "-ac", "1", "-ar", "16000", "pipe:1"],
        input=data, capture_output=True, check=True).stdout
    return np.frombuffer(out, np.int16).astype(np.float32) / 32768.0

@app.get("/health")
def health():
    return {"ok": True, "model": MODEL}

@app.post("/v1/audio/transcriptions")
def transcribe(file: UploadFile = File(...), language: str = Form("id"), authorization: str = Header("")):
    if KEY and authorization != f"Bearer {KEY}":
        raise HTTPException(401, "bad key")
    try:
        audio = load_audio(file.file.read())
    except subprocess.CalledProcessError:
        raise HTTPException(415, "cannot decode audio")
    segs, _ = model.transcribe(audio, language=language or "id", beam_size=1, vad_filter=True, initial_prompt="Operator pabrik melaporkan alasan mesin berhenti: bearing, motor, belt, oli, panas, overheat, korslet, MCB, teknisi, material, gudang, ganti produk, setting, istirahat, makan siang.")
    return {"text": " ".join(s.text.strip() for s in segs)}
