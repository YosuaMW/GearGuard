from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Autentikasi masuk dari backend: header "Authorization: Bearer <AI_SERVICE_KEY>" ---
    # Nilai ini yang diisi backend sebagai AI_API_KEY di .env Raspberry Pi. Kosong = tanpa auth (hanya lokal).
    ai_service_key: str = ""

    # --- AMD Token Factory (satu key dipakai satu tim; JANGAN dibagikan ke backend/Pi) ---
    radeon_api_key: str = ""
    radeon_base_url: str = "https://developer.amd.com.cn/radeon/api/v1"
    analysis_model: str = "Qwen3.8-27B"
    ocr_model: str = "MinerU2.5-Pro"
    # Hanya dipakai bila WHISPER_BASE_URL kosong (fallback transkripsi lewat model audio)
    audio_model: str = "MiMo-V2.6-Flash"
    # Label GPU untuk field usage.gpu (halaman "Running on AMD"). Isi sesuai kenyataan.
    gpu_label: str = "AMD Radeon Cloud"

    # --- Whisper di instance GPU AMD (vLLM, OpenAI-compatible). Kosong = pakai fallback ---
    whisper_base_url: str = ""
    whisper_api_key: str = "EMPTY"
    whisper_model: str = "openai/whisper-large-v3"

    # --- Pengaman kuota: limit Token Factory 30 RPM / 8 concurrent PER KEY (se-tim) ---
    rpm_limit: int = 18
    max_concurrency: int = 3
    max_retries: int = 2
    request_timeout: float = 120.0
    ocr_timeout: float = 600.0

    # --- Batas waktu total per endpoint (backend: classify timeout 20 dtk, transcribe 30 dtk) ---
    classify_budget: float = 15.0
    transcribe_budget: float = 25.0
    explain_budget: float = 45.0

    # --- Perilaku ---
    confidence_threshold: float = 0.6  # hanya informasi; keputusan "Needs review" ada di backend
    ocr_mode: str = "auto"  # auto | always | never (untuk ingest PDF manual)
    ocr_batch_pages: int = 5
    rag_top_k: int = 4

    data_dir: str = "data"
    manuals_dir: str = "data/manuals"
    repair_history_file: str = "data/repair_history.json"
    repair_history_seed: str = "seed/repair_history.sample.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
