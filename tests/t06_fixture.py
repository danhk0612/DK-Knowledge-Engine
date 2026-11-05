"""T06 offline fixtures: real T02 DB, real T05 HTTP server, no model/download."""

from __future__ import annotations

import argparse
import json
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from api.localhost_api import KnowledgeHttpServer
from builder.knowledge_builder import build


class FakeGenerator:
    def generate(self, system: str, user: str) -> str:
        if "3308" not in user:
            raise RuntimeError("fixture received unexpected prompt")
        return "DB 서버 포트 3308을 확인하십시오."


class SilentHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass


def setup_fixture(home: Path, *, web: bool):
    root = home / "sources"
    manuals = root / "example-program" / "manuals"
    rules = root / "example-program" / "rules"
    manuals.mkdir(parents=True)
    rules.mkdir(parents=True)

    doc = manuals / "setup.md"
    doc.write_text(
        "# DB 연결 오류\n\n연결 오류 시 DB 서버 포트 3308을 확인하십시오. "
        "<img src=x onerror=alert(1)>",
        encoding="utf-8",
    )
    (manuals / "setup.md.meta.json").write_text(
        json.dumps({"document_id": "guide", "version_from": "2.0.0", "version_to": "3.0.0"}),
        encoding="utf-8",
    )
    (rules / "db.json").write_text(json.dumps({
        "rule_id": "db-1001",
        "product_id": "example-program",
        "event_id": "connection_failed",
        "error_code": "DB-1001",
        "screen_id": "db_settings",
        "document_id": "guide",
        "title": "데이터베이스 연결 오류",
        "content": "DB 서버 포트 3308을 확인하십시오.",
    }, ensure_ascii=False), encoding="utf-8")

    database = home / "knowledge.db"
    build(root, database)
    api = KnowledgeHttpServer(
        database, port=8765,
        generator=FakeGenerator(),
        allowed_origins=("http://127.0.0.1:8766",),
    )
    servers = [api]
    if web:
        static = Path(__file__).resolve().parent.parent / "integrations" / "web"
        handler = partial(SilentHandler, directory=str(static))
        for port in (8766, 8767):
            servers.append(ThreadingHTTPServer(("127.0.0.1", port), handler))
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    return servers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--web", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        servers = setup_fixture(Path(folder), web=args.web)
        print("T06_FIXTURE_READY", flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    main()
