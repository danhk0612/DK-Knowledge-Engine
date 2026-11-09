"""T21 real on-device Windows embedding smoke (no cloud inference or private data).

Uses a published third-party GGUF only in CI. The input Korean source samples
are synthetic and must not be interpreted as real-customer recall metrics.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from time import perf_counter

from builder.knowledge_builder import build
from embedding.llama_embedder import LlamaEmbedder
from search.knowledge_search import search_documents
from distribution.server_entry import verify_database


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--runtime", type=Path, required=True)
    p.add_argument("--model", type=Path, required=True)
    args = p.parse_args()
    with tempfile.TemporaryDirectory(prefix="dk-t21-") as d:
        root = Path(d)
        src = root / "source" / "camera" / "manuals"
        src.mkdir(parents=True)
        (src / "shutdown.md").write_text(
            "# 장치 제어\n\n전원 버튼을 5초간 길게 눌러 작동을 중지합니다. "
            "표시등이 꺼진 것을 확인하세요.", encoding="utf-8")
        (src / "clock.md").write_text(
            "# 시각 동기화\n\n장치 설정에서 날짜와 시간을 선택하여 "
            "표준시를 지정합니다.", encoding="utf-8")
        (root / "source" / "unrelated" / "manuals").mkdir(parents=True)
        (root / "source" / "unrelated" / "manuals" / "shutdown.md").write_text(
            "다른 제품의 전원 버튼을 누르지 마세요.", encoding="utf-8")
        db = root / "knowledge.db"
        started = perf_counter()
        info = build(root / "source", db, rebuild=True,
                     embedding_runtime=args.runtime, embedding_model=args.model,
                     embedding_profile="e5")
        author_seconds = round(perf_counter() - started, 2)
        embed_info = info["embedding_index"]
        if not embed_info["complete"] or embed_info["dimensions"] != 384:
            raise AssertionError(f"Unexpected embedding metadata: {embed_info}")
        verified = verify_database(db)["embedding"]
        if not verified["complete"] or verified["vectors"] != info["chunks"]:
            raise AssertionError(f"Invalid packaged DB vectors: {verified}")
        with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as cn:
            meta = dict(cn.execute("SELECT key,value FROM embedding_metadata").fetchall())
        if meta["query_prefix"] != "query: " or meta["passage_prefix"] != "passage: ":
            raise AssertionError("E5 asymmetric embedding prefixes not stored")
        query = "기기를 안전하게 끄는 순서가 궁금합니다"
        exact = search_documents(db, product_id="camera", query=query)
        if exact:
            raise AssertionError("Test query unexpectedly matches original lexical FTS")
        encoder = LlamaEmbedder(args.runtime, args.model)
        tick = perf_counter()
        results = search_documents(
            db, product_id="camera", query=query,
            embedder=encoder, min_similarity=0.01, limit=5)
        query_seconds = round(perf_counter() - tick, 2)
        if not results or not any(h["source_path"] == "camera/manuals/shutdown.md" for h in results):
            raise AssertionError("Real semantic retrieval could not recover source chunk")
        if any(h["source_path"].startswith("unrelated/") for h in results):
            raise AssertionError("Cross-product retrieval must not occur")
        # No user documents and no GGUF file bytes in the test report.
        print("T21_REAL_EMBEDDING_SMOKE=" + json.dumps({
            "dimension": embed_info["dimensions"],
            "document_vectors": verified["vectors"],
            "db_bytes": db.stat().st_size,
            "source_found": True,
            "author_seconds": author_seconds,
            "query_seconds": query_seconds,
            "runtime": "llama.cpp v0.8.0",
            "model_variant": "multilingual-e5-small-q8_0",
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
