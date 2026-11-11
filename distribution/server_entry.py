"""Portable Windows entrypoint for the existing T05 API.

The frozen executable is kept under package_root/engine.  All deployment
resources are beside that directory; no target-PC Python installation is needed.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from api.localhost_api import main as api_main


def package_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent
    return Path(__file__).resolve().parent.parent


def verify_database(database: Path) -> dict:
    if not database.is_file():
        raise FileNotFoundError(f"Knowledge database is missing: {database}")
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        integrity = db.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise ValueError("Knowledge database integrity_check failed")
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("Knowledge database foreign key check failed")
        version = db.execute(
            "SELECT value FROM schema_info WHERE key='schema_version'"
        ).fetchone()
        if version is None or version[0] != "1":
            raise ValueError("Unsupported knowledge database schema version")
        # Enforce the expected T02/T03 schema, not just a user-controlled version flag.
        for table in ("documents", "chunks", "help_rules", "chunks_fts"):
            match = db.execute(
                "SELECT 1 FROM sqlite_master WHERE name=?", (table,)
            ).fetchone()
            if match is None:
                raise ValueError(f"Required knowledge table is missing: {table}")
        result = {
            "schema_version": version[0],
            "documents": db.execute("SELECT count(*) FROM documents").fetchone()[0],
            "chunks": db.execute("SELECT count(*) FROM chunks").fetchone()[0],
            "rules": db.execute("SELECT count(*) FROM help_rules").fetchone()[0],
        }
        has_vectors = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunk_embeddings'"
        ).fetchone()
        if has_vectors:
            metadata = dict(db.execute("SELECT key,value FROM embedding_metadata").fetchall())
            count = db.execute("SELECT count(*) FROM chunk_embeddings").fetchone()[0]
            dimensions = int(metadata.get("dimensions", "0"))
            consistent = (16 <= dimensions <= 4096 and
                db.execute(
                    "SELECT count(*) FROM chunk_embeddings "
                    "WHERE dimensions != ? OR length(vector) != ?",
                    (dimensions, 4 * dimensions)
                ).fetchone()[0] == 0)
            result["embedding"] = {
                "model_sha256": metadata.get("model_sha256", ""),
                "profile": metadata.get("profile", ""),
                "vectors": count, "dimensions": dimensions,
                "complete": bool(
                    consistent and metadata.get("model_sha256") and
                    count == result["chunks"]
                ),
            }
        return result


def verify_product_database(database: Path, product_id: str) -> dict:
    """Verify that a client knowledge DB contains only its assigned product."""
    if not isinstance(product_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", product_id):
        raise ValueError("Invalid product ID")
    result = verify_database(database)
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        product_counts = dict(db.execute(
            "SELECT product_id, COUNT(*) FROM documents GROUP BY product_id"
        ).fetchall())
        if set(product_counts) != {product_id}:
            raise ValueError("Knowledge DB contains another product or has no documents")
        if db.execute(
            "SELECT COUNT(*) FROM help_rules WHERE product_id != ?", (product_id,)
        ).fetchone()[0]:
            raise ValueError("Knowledge DB contains rules for another product")
    result["product_id"] = product_id
    return result


def scope_product_database(database: Path, product_id: str) -> dict:
    """Remove other products from a *packaging copy*, preserving FTS and optional vectors."""
    # Verify BEFORE changing anything, including that the desired product exists.
    verify_database(database)
    if not isinstance(product_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", product_id):
        raise ValueError("Invalid product ID")
    with closing(sqlite3.connect(database)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        if not db.execute(
            "SELECT 1 FROM documents WHERE product_id=? LIMIT 1", (product_id,)
        ).fetchone():
            raise ValueError("Selected product has no documents; rebuild DB with this product ID")
        with db:
            db.execute(
                "DELETE FROM help_rules WHERE product_id != ?", (product_id,)
            )
            # Cascades delete chunks, search hints and semantic vectors, via existing triggers.
            db.execute("DELETE FROM documents WHERE product_id != ?", (product_id,))
            db.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('integrity-check')")
            if db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='chunk_search_hints_fts'"
            ).fetchone():
                db.execute(
                    "INSERT INTO chunk_search_hints_fts(chunk_search_hints_fts) "
                    "VALUES('integrity-check')"
                )
            if db.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("Product isolation would violate foreign keys")
        db.execute("VACUUM")
    return verify_product_database(database, product_id)


def compact_without_embeddings(database: Path) -> dict:
    """Drop only optional T19 vector tables from a *packaging copy* of the DB.

    Never call on the author's source DB. The command-line entrypoint below
    confines this operation to its own portable package knowledge directory.
    """
    verified = verify_database(database)
    before = database.stat().st_size
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name IN ('chunk_embeddings','embedding_metadata')"
            ).fetchall()
        }
        if tables:
            with connection:
                connection.execute("DROP TABLE IF EXISTS chunk_embeddings")
                connection.execute("DROP TABLE IF EXISTS embedding_metadata")
            connection.execute("VACUUM")
    after = verify_database(database)
    if any(after[key] != verified[key] for key in ("schema_version", "documents", "chunks", "rules")):
        raise ValueError("Compacting removed primary knowledge content")
    return {"before_bytes": before, "after_bytes": database.stat().st_size,
            "removed_vectors": verified.get("embedding", {}).get("vectors", 0)}


def _selected_file(root: Path, value: str, folder: str, suffix: str) -> Path:
    """Resolve a local model/runtime choice strictly inside its package folder."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{folder} selection must be a non-empty path")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != folder:
        raise ValueError(f"{folder} selection must be inside {folder}/")
    target = (root / relative).resolve()
    if not target.is_relative_to((root / folder).resolve()) or target.suffix.lower() != suffix:
        raise ValueError(f"{folder} selection has invalid path or extension")
    if not target.is_file():
        raise FileNotFoundError(f"Selected {folder} file does not exist: {target}")
    return target


def portable_cli(root: Path, settings: dict) -> list[str]:
    """T09: reusable T05 CLI args from user-selected local GGUF and runtime."""
    if not isinstance(settings, dict) or set(settings) - {"port", "allowed_origins", "model", "embedding"}:
        raise ValueError("Unsupported keys in settings.json")
    if not {"port", "allowed_origins"} <= set(settings):
        raise ValueError("settings.json requires port and allowed_origins")
    port = settings["port"]
    origins = settings["allowed_origins"]
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Invalid API port")
    if not isinstance(origins, list) or not all(isinstance(v, str) for v in origins):
        raise ValueError("allowed_origins must be a string array")
    model_cfg = settings.get("model", {})
    if not isinstance(model_cfg, dict):
        raise ValueError("model must be an object")
    defaults = {
        "file": "models/Qwen3-1.7B-Q4_K_M.gguf",
        "runtime": "runtime/llama-completion.exe",
        "threads": 4,
        "context_size": 4096,
        "max_tokens": 192,
        "timeout_seconds": 180,
        "gpu_layers": 0,
        "prompt_mode": "raw_chatml",
    }
    if set(model_cfg) - set(defaults):
        raise ValueError("Unsupported model option")
    options = {**defaults, **model_cfg}
    for key in ("threads", "context_size", "max_tokens", "timeout_seconds"):
        if type(options[key]) is not int or options[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    if type(options["gpu_layers"]) is not int or options["gpu_layers"] < 0:
        raise ValueError("gpu_layers must be a non-negative integer")
    if options["prompt_mode"] not in ("qwen3", "raw_chatml", "jinja"):
        raise ValueError("Unsupported prompt_mode")
    executable = _selected_file(root, options["runtime"], "runtime", ".exe")
    model = _selected_file(root, options["file"], "models", ".gguf")
    cli = [
        "--database", str(root / "knowledge" / "knowledge.db"),
        "--port", str(port),
        "--llama-cli", str(executable),
        "--model", str(model),
        "--threads", str(options["threads"]),
        "--ctx-size", str(options["context_size"]),
        "--max-tokens", str(options["max_tokens"]),
        "--timeout-seconds", str(options["timeout_seconds"]),
        "--gpu-layers", str(options["gpu_layers"]),
        "--prompt-mode", options["prompt_mode"],
    ]
    embedding = settings.get("embedding")
    if embedding is not None:
        if not isinstance(embedding, dict) or set(embedding) != {
                "file", "runtime", "min_similarity"}:
            raise ValueError("Invalid embedding model settings")
        threshold = embedding["min_similarity"]
        if type(threshold) not in (float, int) or not 0.0 < threshold <= 1.0:
            raise ValueError("Embedding minimum similarity must be in (0, 1]")
        embedding_runtime = _selected_file(root, embedding["runtime"], "runtime", ".exe")
        embedding_model = _selected_file(root, embedding["file"], "models", ".gguf")
        cli.extend((
            "--embedding-runtime", str(embedding_runtime),
            "--embedding-model", str(embedding_model),
            "--embedding-min-similarity", str(threshold),
        ))
    for origin in origins:
        cli.extend(("--allow-origin", origin))
    return cli


def run(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description="DK Knowledge Engine portable Windows API")
    parser.add_argument("--verify-db", type=Path, help="Validate a knowledge DB without starting the server")
    parser.add_argument("--compact-no-embeddings", action="store_true",
                        help="Remove optional vector index from this package's DB copy")
    parser.add_argument("--scope-product-id", help="Keep only this product in the package DB copy")
    parser.add_argument("--verify-product-id", help="Require the verified DB to contain one product")
    args = parser.parse_args(argv)
    if args.verify_db is not None and args.compact_no_embeddings:
        parser.error("Use only one database maintenance action")
    if args.scope_product_id and (args.verify_db is not None or args.compact_no_embeddings):
        parser.error("Product isolation cannot be combined with other maintenance actions")
    if args.verify_product_id and args.verify_db is None:
        parser.error("--verify-product-id requires --verify-db")
    if args.scope_product_id:
        # Never accept an arbitrary path for a mutating action.
        base = root if root is not None else package_root()
        try:
            print(json.dumps(scope_product_database(
                base / "knowledge" / "knowledge.db", args.scope_product_id
            )))
            return 0
        except (OSError, sqlite3.Error, ValueError) as exc:
            print(f"Packaged DB product isolation failed: {exc}", file=sys.stderr)
            return 1
    if args.compact_no_embeddings:
        # Do not accept a caller-provided file path: this command may only
        # alter the already copied DB inside the engine's own package root.
        base = root if root is not None else package_root()
        try:
            report = compact_without_embeddings(base / "knowledge" / "knowledge.db")
            print(json.dumps(report))
            return 0
        except (OSError, sqlite3.Error, ValueError) as exc:
            print(f"Packaged DB compaction failed: {exc}", file=sys.stderr)
            return 1
    if args.verify_db is not None:
        try:
            report = (verify_product_database(args.verify_db, args.verify_product_id)
                      if args.verify_product_id else verify_database(args.verify_db))
            print(json.dumps(report, ensure_ascii=False))
            return 0
        except (OSError, sqlite3.Error, ValueError) as exc:
            print(f"Knowledge DB verification failed: {exc}", file=sys.stderr)
            return 1

    base = root if root is not None else package_root()
    try:
        settings = json.loads((base / "config" / "settings.json").read_text(encoding="utf-8"))
        db = base / "knowledge" / "knowledge.db"
        verify_database(db)
        cli = portable_cli(base, settings)
    except (OSError, json.JSONDecodeError, ValueError, sqlite3.Error) as exc:
        print(f"Portable package startup failed: {exc}", file=sys.stderr)
        return 1
    # PyInstaller's Windows bootloader sets a DLL directory inherited by
    # subprocesses. The independent llama.cpp executable must search its own
    # runtime directory rather than the frozen Python engine's _internal DLLs.
    # Restore the standard DLL search order before starting the HTTP server.
    # https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        import ctypes

        if not ctypes.windll.kernel32.SetDllDirectoryW(None):
            raise OSError("Unable to restore native Windows DLL search order")

    # Existing API handles loopback binding and CORS; no new network listeners.
    return api_main(cli)


if __name__ == "__main__":
    raise SystemExit(run())
