"""RAG ringan tanpa embedding (Token Factory tidak menyediakan /v1/embeddings).

Pencarian memakai BM25 murni Python. Cukup untuk 2-3 PDF manual + riwayat perbaikan,
tanpa dependensi tambahan dan tanpa memakai kuota API.
"""
import json
import math
import re
import threading
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

_STOP = set(
    "yang dan di ke dari untuk pada dengan atau ini itu adalah akan dapat dalam oleh juga "
    "the of and to in is a for on with be as are by or an at it".split()
)
_TOKEN = re.compile(r"[a-zA-Z0-9]+")


def tokenize(text: str) -> list[str]:
    return [t for t in (m.lower() for m in _TOKEN.findall(text)) if t not in _STOP and len(t) > 1]


@dataclass
class Chunk:
    id: str
    source: str  # nama file / "riwayat"
    kind: str  # "manual" | "riwayat"
    page: int | None
    text: str


def chunk_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out, cur = [], ""
    for p in paras:
        if cur and len(cur) + len(p) + 2 > size:
            out.append(cur)
            cur = cur[-overlap:] + "\n\n" + p if overlap else p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
        while len(cur) > size * 1.5:  # paragraf sangat panjang
            out.append(cur[:size])
            cur = cur[size - overlap :]
    if cur.strip():
        out.append(cur)
    return out


class RagIndex:
    def __init__(self, data_dir: str):
        self.path = Path(data_dir) / "index.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.chunks: list[Chunk] = []
        self._tf: list[Counter] = []
        self._df: Counter = Counter()
        self._avgdl = 0.0
        self._lock = threading.Lock()
        self._load()

    # ---- persistence ----
    def _load(self) -> None:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self.chunks = [Chunk(**c) for c in raw]
            except (json.JSONDecodeError, TypeError):
                self.chunks = []
        self._rebuild()

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(c) for c in self.chunks], ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def _rebuild(self) -> None:
        self._tf = [Counter(tokenize(c.text)) for c in self.chunks]
        self._df = Counter()
        for tf in self._tf:
            self._df.update(tf.keys())
        total = sum(sum(tf.values()) for tf in self._tf)
        self._avgdl = total / len(self._tf) if self._tf else 0.0

    # ---- mutasi ----
    def remove_source(self, source: str) -> None:
        with self._lock:
            self.chunks = [c for c in self.chunks if c.source != source]
            self._rebuild()
            self._save()

    def add_document(self, source: str, kind: str, pages: list[tuple[int | None, str]]) -> int:
        """Ganti seluruh isi `source` dengan halaman baru. Mengembalikan jumlah chunk."""
        new: list[Chunk] = []
        for page, text in pages:
            for i, piece in enumerate(chunk_text(text)):
                new.append(Chunk(f"{source}#{page or 0}-{i}", source, kind, page, piece))
        with self._lock:
            self.chunks = [c for c in self.chunks if c.source != source] + new
            self._rebuild()
            self._save()
        return len(new)

    # ---- pencarian ----
    def search(self, query: str, k: int = 4, kind: str | None = None, min_score: float = 0.0) -> list[tuple[Chunk, float]]:
        q = tokenize(query)
        n = len(self.chunks)
        if not q or n == 0:
            return []
        k1, b = 1.5, 0.75
        scored: list[tuple[Chunk, float]] = []
        for chunk, tf in zip(self.chunks, self._tf):
            if kind and chunk.kind != kind:
                continue
            dl = sum(tf.values()) or 1
            score = 0.0
            for term in set(q):
                f = tf.get(term, 0)
                if not f:
                    continue
                df = self._df[term]
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                score += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / (self._avgdl or 1)))
            if score > min_score:  # skor absolut tidak stabil untuk korpus kecil; cukup butuh >= 1 kata cocok
                scored.append((chunk, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def stats(self) -> dict:
        sources: dict[str, int] = {}
        for c in self.chunks:
            sources[c.source] = sources.get(c.source, 0) + 1
        return {"chunks": len(self.chunks), "sources": sources}


# ---- riwayat perbaikan ----
def load_repair_history(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def sync_repair_history(index: RagIndex, path: str) -> int:
    """Masukkan riwayat perbaikan ke indeks sebagai sumber bertipe 'riwayat'."""
    records = load_repair_history(path)
    pages = []
    for i, r in enumerate(records, 1):
        text = (
            f"Riwayat perbaikan {r.get('date', '-')} mesin {r.get('machine_id', '-')}. "
            f"Gejala: {r.get('symptom', '')}. Penyebab: {r.get('cause', '')}. Tindakan: {r.get('action', '')}."
        )
        pages.append((i, text))
    if not pages:
        index.remove_source("riwayat")
        return 0
    return index.add_document("riwayat", "riwayat", pages)
