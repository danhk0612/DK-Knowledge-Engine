"""Create a synthetic metadata-only embedding fixture for packaging CI.

The fake .gguf is NOT an inference-capable model; this tests hashes and ZIP
contents only. Never publish the synthetic artifact to customers.
"""
import argparse
import hashlib
import shutil
import sqlite3
import struct
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    if not args.database.is_file() or not args.model.is_file():
        parser.error("Missing source DB or test model")
    if args.output.exists():
        parser.error("Output DB already exists")
    shutil.copyfile(args.database, args.output)
    with sqlite3.connect(args.output) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
            CREATE TABLE embedding_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE chunk_embeddings (
                chunk_id TEXT PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
                dimensions INTEGER NOT NULL,
                vector BLOB NOT NULL
            );
        """)
        model_hash = hashlib.sha256(args.model.read_bytes()).hexdigest()
        meta = {
            "model_sha256": model_hash, "profile": "generic",
            "query_prefix": "", "passage_prefix": "", "dimensions": "16",
        }
        db.executemany(
            "INSERT INTO embedding_metadata(key,value) VALUES(?,?)",
            list(meta.items()),
        )
        vec = struct.pack("<16f", 1.0, *([0.0] * 15))
        ids = [x[0] for x in db.execute("SELECT chunk_id FROM chunks").fetchall()]
        db.executemany(
            "INSERT INTO chunk_embeddings(chunk_id,dimensions,vector) VALUES(?,16,?)",
            [(id_, vec) for id_ in ids],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
