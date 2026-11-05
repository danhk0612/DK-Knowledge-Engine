"""Generate representative disposable T07 knowledge DBs using the actual T02 builder."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from builder.knowledge_builder import build


def produce(destination: Path, *, port: int = 3308) -> None:
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / "sources"
        docs = source / "example-program" / "manuals"
        rules = source / "example-program" / "rules"
        docs.mkdir(parents=True)
        rules.mkdir(parents=True)
        (docs / "setup.md").write_text(
            "# 데이터베이스 연결\n\n연결 오류 시 DB 서버 포트 "
            + str(port) + "을 확인하십시오.",
            encoding="utf-8",
        )
        (docs / "setup.md.meta.json").write_text(
            json.dumps({
                "document_id": "setup-guide",
                "version_from": "2.0.0",
                "version_to": "3.0.0",
            }), encoding="utf-8",
        )
        (rules / "db.json").write_text(
            json.dumps({
                "rule_id": "db-1001",
                "product_id": "example-program",
                "event_id": "connection_failed",
                "error_code": "DB-1001",
                "document_id": "setup-guide",
                "title": "DB 연결 실패",
                "content": "DB 서버 포트 " + str(port) + " 확인",
            }, ensure_ascii=False), encoding="utf-8",
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        build(source, destination, rebuild=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--port", type=int, default=3308)
    arguments = parser.parse_args()
    produce(arguments.output, port=arguments.port)


if __name__ == "__main__":
    main()
