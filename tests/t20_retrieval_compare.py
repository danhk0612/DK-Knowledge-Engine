"""Local, privacy-preserving before/after retrieval benchmark for approved cases.

Run with an explicit labeled question set. The report stores only case IDs and
pass/fail flags, not private questions, documents, answers, or source paths.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
from contextlib import closing
from pathlib import Path
from time import perf_counter
from typing import Any

from embedding.llama_embedder import LlamaEmbedder, sha256_file
from search.knowledge_search import search_documents


def read_cases(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, list) or not value:
        raise ValueError("Expected a non-empty JSON array")
    seen = set()
    for case in value:
        if not isinstance(case, dict) or set(case) - {
            "id", "product_id", "query", "expected_source", "version"
        }:
            raise ValueError("Unknown benchmark case fields")
        for name in ("id", "product_id", "query"):
            if not isinstance(case.get(name), str) or not case[name].strip():
                raise ValueError(f"Case {name} must be non-blank")
        if case["id"] in seen:
            raise ValueError("Duplicate benchmark ID")
        seen.add(case["id"])
        if "expected_source" not in case:
            raise ValueError("Every benchmark case requires expected_source (null for no evidence)")
        if (case["expected_source"] is not None and (
                not isinstance(case["expected_source"], str)
                or not case["expected_source"].strip())):
            raise ValueError("Case expected_source must be a nonblank path or null")
        if case.get("version") is not None and not isinstance(case["version"], str):
            raise ValueError("Case version must be a string or null")
    return value


def evaluate(db: Path, cases: list[dict], *, embedder=None) -> dict:
    results = []
    times = []
    for case in cases:
        started = perf_counter()
        hits = search_documents(
            db, product_id=case["product_id"], query=case["query"],
            version=case.get("version"), limit=5, embedder=embedder,
        )
        elapsed = round((perf_counter() - started) * 1000, 2)
        times.append(elapsed)
        expected = case.get("expected_source")
        paths = [hit["source_path"] for hit in hits]
        correct = (not paths) if expected is None else expected in paths
        results.append({
            "case_id": case["id"],
            "passed": correct,
            "top1": bool(expected is not None and paths and paths[0] == expected),
            "top5": bool(expected is not None and expected in paths),
            "returned_results": len(paths),
            "latency_ms": elapsed,
        })
    return {
        "db_sha256": sha256_file(db),
        "db_bytes": db.stat().st_size,
        "cases": len(cases),
        "passed": sum(x["passed"] for x in results),
        "top1": sum(x["top1"] for x in results),
        "top5": sum(x["top5"] for x in results),
        "median_latency_ms": round(statistics.median(times), 2),
        "results": results,
    }


def compare(original: Path, improved: Path, cases: list[dict], *, embedder=None) -> dict:
    baseline = evaluate(original, cases)
    candidate = evaluate(improved, cases, embedder=embedder)
    return {
        "version": 1,
        "baseline": baseline,
        "candidate": candidate,
        "change": {
            "passed": candidate["passed"] - baseline["passed"],
            "top1": candidate["top1"] - baseline["top1"],
            "top5": candidate["top5"] - baseline["top5"],
            "db_bytes": candidate["db_bytes"] - baseline["db_bytes"],
            "median_latency_ms": round(candidate["median_latency_ms"] - baseline["median_latency_ms"], 2),
        },
        "limitations": [
            "Ground-truth source paths must be manually validated against the original PDFs.",
            "A correct source does not prove the generator's answer is correct.",
            "Actual model and hardware latency will differ from synthetic cases.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-db", required=True, type=Path)
    parser.add_argument("--candidate-db", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--embedding-runtime", type=Path)
    parser.add_argument("--embedding-model", type=Path)
    args = parser.parse_args()
    for path in (args.baseline_db, args.candidate_db, args.cases):
        if not path.is_file():
            parser.error(f"File does not exist: {path}")
    if args.output.exists():
        parser.error("Output report already exists; refuse to overwrite")
    if (args.embedding_runtime is None) != (args.embedding_model is None):
        parser.error("Embedding model/runtime must be supplied together")
    model = None
    if args.embedding_model:
        with closing(sqlite3.connect(args.candidate_db.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            meta = dict(db.execute("SELECT key,value FROM embedding_metadata").fetchall())
            embedded = db.execute("SELECT count(*) FROM chunk_embeddings").fetchone()[0]
            total = db.execute("SELECT count(*) FROM chunks").fetchone()[0]
        if meta.get("model_sha256") != sha256_file(args.embedding_model) or embedded != total:
            parser.error("Encoder must match a complete candidate knowledge index")
        model = LlamaEmbedder(args.embedding_runtime, args.embedding_model)
    result = compare(args.baseline_db, args.candidate_db, read_cases(args.cases),
                     embedder=model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("T20_RETRIEVAL_COMPARE=" + json.dumps({
        "baseline_passed": result["baseline"]["passed"],
        "candidate_passed": result["candidate"]["passed"],
        "change": result["change"],
    }, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
