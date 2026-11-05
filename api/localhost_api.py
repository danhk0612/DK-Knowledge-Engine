"""T05 local-only JSON HTTP API, backed by T02/T03/T04.

No external service, non-loopback binding, container, or account infrastructure.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import threading
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from llm.local_llm import LlamaCli, TextGenerator, answer_from_knowledge
from search.knowledge_search import match_event, search_documents

ENGINE_VERSION = "0.1.0"
MAX_REQUEST_BYTES = 32 * 1024
ROUTES = frozenset({"/search", "/chat", "/event"})


def _schema_version(database: Path) -> str:
    if not database.is_file():
        raise FileNotFoundError(database)
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        row = db.execute(
            "SELECT value FROM schema_info WHERE key='schema_version'"
        ).fetchone()
        if row is None or row[0] != "1":
            raise ValueError("Unsupported knowledge database schema")
        return row[0]


def _origin_value(value: str) -> str:
    """Reject origin patterns or URLs with paths: allow only exact HTTP(S) origins."""
    parsed = urlsplit(value)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password or parsed.path or
            parsed.query or parsed.fragment or value == "null"):
        raise ValueError("Allowed origins must be exact http(s) origins without paths")
    try:
        _ = parsed.port  # Validate the port syntax.
    except ValueError as exc:
        raise ValueError("Invalid allowed origin port") from exc
    if value != f"{parsed.scheme}://{parsed.netloc}":
        raise ValueError("Allowed origins must not have a trailing slash")
    return value


def _required(body: dict[str, Any], name: str) -> str:
    value = body.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    if len(value) > 4000:
        raise ValueError(f"{name} is too long")
    return value


def _optional(body: dict[str, Any], name: str) -> str | None:
    value = body.get(name)
    if value is None:
        return None
    return _required(body, name)


class KnowledgeHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self, database: str | Path, *, port: int = 8765,
        generator: TextGenerator | None = None,
        allowed_origins: tuple[str, ...] = (),
    ) -> None:
        if not isinstance(port, int) or port < 0 or port > 65535:
            raise ValueError("Port must be 0..65535")
        self.database = Path(database).resolve()
        self.knowledge_version = _schema_version(self.database)
        self.generator = generator
        self.chat_lock = threading.Lock()
        self.allowed_origins = frozenset(_origin_value(origin) for origin in allowed_origins)
        # Binding ONLY to the IPv4 loopback address is an explicit security boundary.
        super().__init__(("127.0.0.1", port), KnowledgeHandler)

    def origin_allowed(self, origin: str) -> bool:
        return (origin == f"http://127.0.0.1:{self.server_port}"
                or origin in self.allowed_origins)


class KnowledgeHandler(BaseHTTPRequestHandler):
    server: KnowledgeHttpServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        # Avoid recording user queries, credentials or request bodies.
        pass

    def _reply(
        self, status: int, payload: dict[str, Any] | None = None, *,
        preflight: bool = False
    ) -> None:
        raw = (json.dumps(payload, ensure_ascii=False).encode("utf-8")
               if payload is not None else b"")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Vary", "Origin")
        origin = self.headers.get("Origin")
        if origin is not None and self.server.origin_allowed(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            if preflight:
                self.send_header("Access-Control-Allow-Methods", "POST")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Access-Control-Max-Age", "600")
                if self.headers.get("Access-Control-Request-Private-Network") == "true":
                    self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()
        if raw:
            self.wfile.write(raw)

    def _reject(self, status: int, reason: str) -> None:
        self.close_connection = True
        self._reply(status, {"error": reason})

    def _access_ok(self) -> bool:
        expected_host = f"127.0.0.1:{self.server.server_port}"
        hosts = self.headers.get_all("Host", [])
        if len(hosts) != 1 or hosts[0] != expected_host:
            self._reject(403, "invalid_host")
            return False
        origins = self.headers.get_all("Origin", [])
        if len(origins) > 1:
            self._reject(403, "origin_not_allowed")
            return False
        origin = origins[0] if origins else None
        if origin is not None and not self.server.origin_allowed(origin):
            self._reject(403, "origin_not_allowed")
            return False
        return True

    def do_OPTIONS(self) -> None:
        if not self._access_ok():
            return
        if self.path not in ROUTES:
            self._reject(404, "not_found")
            return
        if not self.headers.get("Origin"):
            self._reject(403, "origin_required")
            return
        if self.headers.get("Access-Control-Request-Method") != "POST":
            self._reject(405, "method_not_allowed")
            return
        requested_headers = {
            header.strip().lower()
            for header in self.headers.get("Access-Control-Request-Headers", "").split(",")
            if header.strip()
        }
        if not requested_headers.issubset({"content-type"}):
            self._reject(403, "headers_not_allowed")
            return
        self._reply(204, preflight=True)

    def do_GET(self) -> None:
        if not self._access_ok():
            return
        if self.path != "/health":
            self._reject(404, "not_found")
            return
        try:
            version = _schema_version(self.server.database)
        except (OSError, sqlite3.Error, ValueError):
            self._reply(503, {"status": "unavailable", "error": "knowledge_unavailable"})
            return
        self._reply(200, {
            "status": "ready",
            "engine_version": ENGINE_VERSION,
            "knowledge_version": version,
            "llm_ready": self.server.generator is not None,
        })

    def _json_body(self) -> dict[str, Any]:
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("transfer_encoding_not_supported")
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise TypeError("json_content_type_required")
        length_str = self.headers.get("Content-Length", "")
        if not length_str.isascii() or not length_str.isdecimal():
            raise ValueError("invalid_content_length")
        length = int(length_str)
        if length == 0:
            raise ValueError("empty_json_body")
        if length > MAX_REQUEST_BYTES:
            raise OverflowError("request_too_large")
        try:
            obj = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid_json") from exc
        if not isinstance(obj, dict):
            raise ValueError("json_object_required")
        return obj

    def do_POST(self) -> None:
        if not self._access_ok():
            return
        if self.path not in ROUTES:
            self._reject(404, "not_found")
            return
        try:
            data = self._json_body()
            keys = {
                "/search": {"product_id", "version", "query"},
                "/chat": {"product_id", "version", "question"},
                "/event": {"product_id", "version", "event_id", "error_code", "screen_id"},
            }[self.path]
            if set(data) - keys:
                raise ValueError("unexpected_fields")
            product_id = _required(data, "product_id")
            version = _optional(data, "version")

            if self.path == "/search":
                results = search_documents(
                    self.server.database, product_id=product_id,
                    query=_required(data, "query"), version=version,
                )
                self._reply(200, {"results": results})
            elif self.path == "/event":
                result = match_event(
                    self.server.database, product_id=product_id, version=version,
                    event_id=_optional(data, "event_id"),
                    error_code=_optional(data, "error_code"),
                    screen_id=_optional(data, "screen_id"),
                )
                self._reply(200, result)
            else:
                question = _required(data, "question")
                if self.server.generator is None:
                    self._reply(503, {"error": "llm_unavailable"})
                elif not self.server.chat_lock.acquire(blocking=False):
                    self._reply(429, {"error": "llm_busy"})
                else:
                    try:
                        result = answer_from_knowledge(
                            self.server.database, product_id=product_id,
                            question=question, version=version,
                            generator=self.server.generator,
                        )
                    finally:
                        self.server.chat_lock.release()
                    self._reply(200, result)
        except OverflowError:
            self._reject(413, "request_too_large")
        except TypeError:
            self._reject(415, "json_content_type_required")
        except ValueError as exc:
            self._reject(400, str(exc))
        except (sqlite3.Error, OSError):
            self._reject(503, "knowledge_unavailable")
        except (TimeoutError, subprocess.TimeoutExpired):
            self._reject(504, "llm_timeout")
        except RuntimeError:
            self._reject(503, "llm_inference_failed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline loopback-only knowledge HTTP API")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--llama-cli", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--ctx-size", type=int, default=4096)
    parser.add_argument("--max-tokens", type=int, default=192)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--gpu-layers", type=int, default=0)
    parser.add_argument("--prompt-mode", choices=("qwen3", "raw_chatml"), default="qwen3")
    parser.add_argument("--allow-origin", action="append", default=[], help="Exact allowed browser origin")
    args = parser.parse_args(argv)
    if (args.llama_cli is None) != (args.model is None):
        parser.error("--llama-cli and --model must be supplied together")
    generator = LlamaCli(
        args.llama_cli, args.model, threads=args.threads, ctx_size=args.ctx_size,
        max_tokens=args.max_tokens, timeout_seconds=args.timeout_seconds,
        gpu_layers=args.gpu_layers, prompt_mode=args.prompt_mode,
    ) if args.model is not None else None
    with KnowledgeHttpServer(
        args.database, port=args.port,
        generator=generator, allowed_origins=tuple(args.allow_origin),
    ) as server:
        print(f"Knowledge API listening on http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
