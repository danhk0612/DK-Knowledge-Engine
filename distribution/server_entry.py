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
    if not isinstance(settings, dict) or set(settings) - {"port", "allowed_origins", "model"}:
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
    for origin in origins:
        cli.extend(("--allow-origin", origin))
    return cli


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
