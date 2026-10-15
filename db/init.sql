-- Skema lengkap GearGuard (gabungan semua ALTER sampai 13 Okt 2026).
-- Untuk instalasi baru: psql "$DATABASE_URL" -f db/init.sql

CREATE TABLE IF NOT EXISTS machines (
  machine_id    TEXT PRIMARY KEY,
  name          TEXT,
  source        TEXT DEFAULT 'live',          -- live | replay
  status        TEXT DEFAULT 'unknown',       -- running | anomaly | stopped
  anomaly_score REAL,
  last_seen     TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS telemetry (
  ts         TIMESTAMPTZ NOT NULL,
  machine_id TEXT NOT NULL,
  current_a  DOUBLE PRECISION,
  vib_rms    DOUBLE PRECISION,
  temp_c     DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS telemetry_machine_ts ON telemetry (machine_id, ts DESC);

CREATE TABLE IF NOT EXISTS events (
  id            SERIAL PRIMARY KEY,
  machine_id    TEXT REFERENCES machines,
  start_ts      TIMESTAMPTZ NOT NULL,
  end_ts        TIMESTAMPTZ,
  transcript    TEXT,
  category      TEXT,
  confidence    REAL,
  needs_review  BOOLEAN DEFAULT FALSE,
  tg_message_id BIGINT,                       -- pesan pertanyaan di Telegram
  voice_path    TEXT                          -- file voice note operator
);

CREATE TABLE IF NOT EXISTS alerts (
  id            SERIAL PRIMARY KEY,
  machine_id    TEXT REFERENCES machines,
  ts            TIMESTAMPTZ NOT NULL,
  score         REAL,
  explanation   TEXT,
  sources       JSONB,
  features      JSONB,                        -- nilai z per sensor
  resolved_ts   TIMESTAMPTZ,
  tg_message_id BIGINT
);

CREATE TABLE IF NOT EXISTS baselines (
  machine_id  TEXT PRIMARY KEY REFERENCES machines,
  stats       JSONB,                          -- median & scale per sensor
  computed_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO machines (machine_id, name, source) VALUES
  ('m1', 'Conveyor motor', 'live'),
  ('m2', 'Pump',  'replay'),
  ('m3', 'Mixer',   'replay'),
  ('m4', 'Compressor',   'replay')
ON CONFLICT (machine_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS ai_calls (
  id                SERIAL PRIMARY KEY,
  ts                TIMESTAMPTZ DEFAULT now(),
  endpoint          TEXT,       -- transcribe | classify | explain
  model             TEXT,
  latency_ms        INT,
  prompt_tokens     INT,
  completion_tokens INT,
  ok                BOOLEAN,
  mock              BOOLEAN,
  error             TEXT
);
