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
        # Exact Windows acceptance fixture: Admin-built manual-test DB search
        # succeeds, so the real generation path must also quote its code.
        acceptance_manuals = tmp / "sources" / "manual-test" / "manuals"
        acceptance_manuals.mkdir(parents=True)
        (acceptance_manuals / "dk-test.md").write_text(
            "# DK local acceptance test\n\n"
            "설치 확인 코드 DKTEST-3308. 이 파일은 인공 테스트 문서입니다.",
            encoding="utf-8",
        )
        db = tmp / "knowledge.db"
        build(tmp / "sources", db)
        runner = LlamaCli(args.llama_cli, args.model, threads=2, max_tokens=128, timeout_seconds=240)
        # Diagnostic control: can this model extract an explicit value at all?
        control = runner.generate(
            "답변은 간단한 한국어 한 문장으로 하세요.",
            "매뉴얼: 연결 실패 시 DB 서버 포트 3308을 확인하십시오. 질문: 확인할 포트 번호는? 답변:",
        )
        print("DIRECT_CONTROL_ANSWER:", repr(control))
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
        assert "Loading model..." not in answer["answer"], answer
        assert "<references>" not in answer["answer"], answer
        assert "Exiting..." not in answer["answer"], answer
        print(json.dumps(answer, ensure_ascii=False, indent=2))

        # The Windows Client defaults to raw_chatml; exercise the same mode
        # with the exact field-report question and artificial source text.
        raw_runner = LlamaCli(
            args.llama_cli, args.model, threads=2, max_tokens=384,
            timeout_seconds=240, prompt_mode="raw_chatml",
        )
        exact = answer_from_knowledge(
            db,
            product_id="manual-test",
            question="설치 확인 코드",
            generator=raw_runner,
        )
        assert exact["grounded"], exact
        assert exact["sources"] and exact["sources"][0]["source_path"] == "manual-test/manuals/dk-test.md", exact
        assert "DKTEST-3308" in exact["answer"], exact
        assert "</think>" not in exact["answer"] and "<think>" not in exact["answer"], exact
        print("WINDOWS_ACCEPTANCE_RAW_CHATML_OK", json.dumps(exact, ensure_ascii=False))


if __name__ == "__main__":
    main()
