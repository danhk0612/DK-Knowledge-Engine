"""Build optional semantic vectors on a capable author PC.

Only a compact compatible *query* GGUF is needed on user PCs. The large author
LLM for question-generation is completely independent from this encoder.
"""
from __future__ import annotations

import json
import sqlite3
import struct
from contextlib import closing
from pathlib import Path

from embedding.llama_embedder import LlamaEmbedder, sha256_file

SCHEMA = """
CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id TEXT PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    dimensions INTEGER NOT NULL CHECK(dimensions >= 16 AND dimensions <= 4096),
    vector BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS embedding_metadata (
    key TEXT PRIMARY KEY, value TEXT NOT NULL
);
"""


def embed_database(
    database: Path, *, runtime: Path, model: Path, profile: str = "generic",
    gpu_layers: int = 0, max_chunks: int = 0,
) -> dict:
    if profile not in ("generic", "e5"):
        raise ValueError("Embedding profile must be generic or e5")
    if max_chunks < 0:
        raise ValueError("max_chunks must be non-negative")
    author = LlamaEmbedder(runtime, model, gpu_layers=gpu_layers)
    model_hash = sha256_file(model)
    prefixes = ("query: ", "passage: ") if profile == "e5" else ("", "")
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(SCHEMA)
        existing = dict(connection.execute(
            "SELECT key, value FROM embedding_metadata").fetchall())
        reset = (existing.get("model_sha256") != model_hash or
                 existing.get("profile") != profile)
        with connection:
            if reset:
                connection.execute("DELETE FROM chunk_embeddings")
                connection.execute("DELETE FROM embedding_metadata")
            rows = connection.execute("""
                SELECT c.chunk_id, c.content
                FROM chunks c
                LEFT JOIN chunk_embeddings e ON e.chunk_id = c.chunk_id
                WHERE e.chunk_id IS NULL
                ORDER BY c.document_id, c.sequence
            """).fetchall()
            if max_chunks:
                rows = rows[:max_chunks]
            dimensions = int(existing.get("dimensions", "0")) if not reset else 0
            indexed = 0
            for chunk_id, content in rows:
                vector = author.encode(prefixes[1] + (content or "")[:3200])
                if dimensions and len(vector) != dimensions:
                    raise ValueError("Embedding dimension changed during indexing")
                dimensions = len(vector)
                blob = struct.pack("<" + "f" * dimensions, *vector)
                connection.execute(
                    "INSERT INTO chunk_embeddings(chunk_id,dimensions,vector) VALUES(?,?,?)",
                    (chunk_id, dimensions, blob),
                )
                indexed += 1
            if dimensions:
                values = {
                    "model_sha256": model_hash,
                    "profile": profile,
                    "query_prefix": prefixes[0],
                    "passage_prefix": prefixes[1],
                    "dimensions": str(dimensions),
                }
                for key, value in values.items():
                    connection.execute(
                        "INSERT OR REPLACE INTO embedding_metadata(key,value) VALUES(?,?)",
                        (key, value),
                    )
            total = connection.execute("SELECT count(*) FROM chunk_embeddings").fetchone()[0]
        return {"indexed": indexed, "total": total, "dimensions": dimensions,
                "profile": profile, "complete": total == connection.execute(
                    "SELECT count(*) FROM chunks").fetchone()[0]}
