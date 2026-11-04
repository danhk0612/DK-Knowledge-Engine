"""Portable Windows entrypoint for the existing T05 API.

The frozen executable is kept under package_root/engine.  All deployment
resources are beside that directory; no target-PC Python installation is needed.
"""

from __future__ import annotations

import argparse
import json
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
        return {
            "schema_version": version[0],
            "documents": db.execute("SELECT count(*) FROM documents").fetchone()[0],
            "chunks": db.execute("SELECT count(*) FROM chunks").fetchone()[0],
            "rules": db.execute("SELECT count(*) FROM help_rules").fetchone()[0],
        }


def run(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description="DK Knowledge Engine portable Windows API")
    parser.add_argument("--verify-db", type=Path, help="Validate a knowledge DB without starting the server")
    args = parser.parse_args(argv)
    if args.verify_db is not None:
        try:
            print(json.dumps(verify_database(args.verify_db), ensure_ascii=False))
            return 0
        except (OSError, sqlite3.Error, ValueError) as exc:
            print(f"Knowledge DB verification failed: {exc}", file=sys.stderr)
            return 1

    base = root if root is not None else package_root()
    try:
        settings = json.loads((base / "config" / "settings.json").read_text(encoding="utf-8"))
        if not isinstance(settings, dict) or set(settings) != {"port", "allowed_origins"}:
            raise ValueError("settings.json must contain only port and allowed_origins")
        port = settings["port"]
        origins = settings["allowed_origins"]
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Invalid API port")
        if not isinstance(origins, list) or not all(isinstance(v, str) for v in origins):
            raise ValueError("allowed_origins must be a string array")

        db = base / "knowledge" / "knowledge.db"
        verify_database(db)
        executable = base / "runtime" / "llama-completion.exe"
        model = base / "models" / "Qwen3-1.7B-Q4_K_M.gguf"
        if not executable.is_file() or not model.is_file():
            raise FileNotFoundError("Required local CPU runtime/model is missing")
        cli = [
            "--database", str(db),
            "--port", str(port),
            "--llama-cli", str(executable),
            "--model", str(model),
        ]
        for origin in origins:
            cli.extend(("--allow-origin", origin))
    except (OSError, json.JSONDecodeError, ValueError, sqlite3.Error) as exc:
        print(f"Portable package startup failed: {exc}", file=sys.stderr)
        return 1
    # Existing API handles loopback binding and CORS; no new network listeners.
    return api_main(cli)


if __name__ == "__main__":
    raise SystemExit(run())
