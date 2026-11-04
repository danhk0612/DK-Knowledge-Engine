"""Optional on-demand real llama.cpp + Qwen3 GGUF CPU inference smoke test.

Run only when the GGUF and llama-cli are already present. Never downloads files.
"""

import argparse
import json
import tempfile
from pathlib import Path

from builder.knowledge_builder import build
from llm.local_llm import LlamaCli, answer_from_knowledge


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llama-cli", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as root:
        tmp = Path(root)
        manuals = tmp / "sources" / "example-program" / "manuals"
        manuals.mkdir(parents=True)
        (manuals / "setup.md").write_text(
            "# 데이터베이스 연결 오류\n\n연결 실패 시에는 DB 서버 포트 3308을 확인하십시오.",
            encoding="utf-8",
        )
        db = tmp / "knowledge.db"
        build(tmp / "sources", db)
        runner = LlamaCli(args.llama_cli, args.model, threads=2, max_tokens=128, timeout_seconds=240)
        answer = answer_from_knowledge(
            db,
            product_id="example-program",
            question="데이터베이스 연결 오류가 나면 어떤 포트를 확인해야 하나요?",
            generator=runner,
        )
        # This checks a single generated example, not broad Korean-answer quality.
        assert answer["grounded"], answer
        assert answer["sources"] and answer["sources"][0]["source_path"].endswith("setup.md"), answer
        assert "3308" in answer["answer"], answer
        print(json.dumps(answer, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
