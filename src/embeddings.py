"""SQLite storage and embedding generation for extracted records."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import struct
from collections.abc import Iterable

from .models import Record


def _default_embedding(text: str, dim: int = 384) -> list[float]:
    """Deterministic fallback embedding (no ML deps required).

    Produces a stable vector from a hash of the text so the same input always
    yields the same embedding. Suitable for dedup and rough similarity without
    installing sentence-transformers.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = []
    for i in range(dim):
        byte = digest[i % len(digest)]
        values.append((byte - 128) / 128.0)
    return values


class EmbeddingStore:
    """SQLite-backed store for records with optional embeddings."""

    def __init__(self, db_path: str = "sabi_records.sqlite", embedding_dim: int = 384):
        self.db_path = db_path
        self.embedding_dim = embedding_dim
        self._embed_fn = self._load_embedder()
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _load_embedder(self):
        """Prefer sentence-transformers; fall back to a deterministic hash."""
        try:  # pragma: no cover - optional dependency
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]  # noqa: I001

            model = SentenceTransformer("all-MiniLM-L6-v2")

            def embed(text: str) -> list[float]:
                vec = model.encode(text, normalize_embeddings=True)
                return [float(v) for v in vec]

            return embed
        except Exception:  # noqa: BLE001
            return lambda text: _default_embedding(text, self.embedding_dim)

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS records (
                cif           TEXT PRIMARY KEY,
                name          TEXT,
                address       TEXT,
                city          TEXT,
                province      TEXT,
                postal_code   TEXT,
                phone         TEXT,
                activity      TEXT,
                detail_url    TEXT,
                record_json   TEXT,
                embedding     BLOB,
                created_at    TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_records_city ON records(city);
            CREATE INDEX IF NOT EXISTS idx_records_name ON records(name);
            """
        )
        self._conn.commit()

    def upsert(self, record: Record) -> None:
        """Insert or replace a record, computing its embedding from name+activity.

        The full record (all fields + extras) is serialized to JSON in
        *record_json* so nothing is lost during storage.
        """
        text = " ".join(filter(None, [record.name, record.activity, record.city]))
        embedding = self._embed_fn(text)
        blob = self._serialize_embedding(embedding)
        record_json = json.dumps(record.to_row(), ensure_ascii=False)
        self._conn.execute(
            """
            INSERT INTO records
                (cif, name, address, city, province, postal_code, phone,
                 activity, detail_url, record_json, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cif) DO UPDATE SET
                name=excluded.name,
                address=excluded.address,
                city=excluded.city,
                province=excluded.province,
                postal_code=excluded.postal_code,
                phone=excluded.phone,
                activity=excluded.activity,
                detail_url=excluded.detail_url,
                record_json=excluded.record_json,
                embedding=excluded.embedding,
                created_at=datetime('now')
            """,
            (
                record.cif or record.name,
                record.name,
                record.address,
                record.city,
                record.province,
                record.postal_code,
                record.phone,
                record.activity,
                record.detail_url,
                record_json,
                blob,
            ),
        )
        self._conn.commit()

    def upsert_many(self, records: Iterable[Record]) -> int:
        count = 0
        for record in records:
            self.upsert(record)
            count += 1
        return count

    def all(self) -> list[dict]:
        cur = self._conn.execute("SELECT record_json FROM records ORDER BY name")
        rows = []
        for (json_str,) in cur.fetchall():
            try:
                rows.append(json.loads(json_str))
            except (TypeError, json.JSONDecodeError):
                continue
        return rows

    def get(self, cif: str) -> dict | None:
        cur = self._conn.execute(
            "SELECT record_json FROM records WHERE cif = ?", (cif,)
        )
        row = cur.fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            return None

    def delete(self, cif: str) -> bool:
        cur = self._conn.execute("DELETE FROM records WHERE cif = ?", (cif,))
        self._conn.commit()
        return cur.rowcount > 0

    def count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM records")
        return cur.fetchone()[0]

    def search_similar(self, query: str, limit: int = 10) -> list[dict]:
        """Return records ordered by cosine similarity to *query* (SQLite fallback).

        Without the sqlite-vec extension this computes similarity in Python over
        all stored embeddings. Fine for modest datasets.
        """

        q_emb = self._embed_fn(query)
        rows = self._conn.execute(
            "SELECT record_json, embedding FROM records"
        ).fetchall()

        scored = []
        for json_str, blob in rows:
            emb = self._deserialize_embedding(blob)
            if emb is None:
                continue
            sim = self._cosine(q_emb, emb)
            try:
                record = json.loads(json_str)
            except (TypeError, json.JSONDecodeError):
                continue
            scored.append((sim, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [record for _, record in scored[:limit]]

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ #
    # embedding helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _serialize_embedding(vec: list[float]) -> bytes:
        return struct.pack(f"<{len(vec)}f", *vec)

    @staticmethod
    def _deserialize_embedding(blob: bytes | None) -> list[float] | None:
        if not blob:
            return None
        n = len(blob) // 4
        return list(struct.unpack(f"<{n}f", blob))

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
