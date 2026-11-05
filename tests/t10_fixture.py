"""T10 non-customer evaluation fixture from entirely synthetic manuals.

Only used on developer/CI machines; never included in the deployed Knowledge DB.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from builder.knowledge_builder import build


def produce(destination: Path) -> None:
    with tempfile.TemporaryDirectory() as workspace:
        source = Path(workspace) / "sources"

        def document(product: str, name: str, text: str, document_id: str,
                     lower: str, upper: str) -> None:
            path = source / product / "manuals" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            path.with_name(path.name + ".meta.json").write_text(
                json.dumps({
                    "document_id": document_id,
                    "version_from": lower,
                    "version_to": upper,
                }, ensure_ascii=False), encoding="utf-8",
            )

        document(
            "product-alpha", "database.md",
            "# 데이터베이스 연결 오류\n\n연결 오류 발생 시 데이터베이스 서버 포트 3308을 확인합니다.",
            "alpha-db", "2.0.0", "3.0.0",
        )
        document(
            "product-alpha", "legacy.md",
            "# 이전 버전 연결 오류\n\n연결 오류 발생 시 구버전 서버 포트 3310을 확인합니다.",
            "alpha-legacy", "1.0.0", "1.9.9",
        )
        document(
            "product-beta", "database.md",
            "# 데이터베이스 연결 오류\n\n연결 오류 발생 시 데이터베이스 서버 포트 9999를 확인합니다.",
            "beta-db", "2.0.0", "3.0.0",
        )
        for product, document_id, rule_id, port in (
            ("product-alpha", "alpha-db", "alpha-db-1001", 3308),
            ("product-beta", "beta-db", "beta-db-1001", 9999),
        ):
            target = source / product / "rules" / "errors.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({
                "rule_id": rule_id,
                "product_id": product,
                "event_id": "connection_failed",
                "error_code": "DB-1001",
                "document_id": document_id,
                "title": "연결 오류",
                "content": f"데이터베이스 서버 포트 {port}를 확인하십시오.",
            }, ensure_ascii=False), encoding="utf-8")
        destination.parent.mkdir(parents=True, exist_ok=True)
        build(source, destination, rebuild=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    produce(args.output)


if __name__ == "__main__":
    main()
