"""T04 unit and Builder/Search integration tests; no model downloads."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from builder.knowledge_builder import build
from llm.local_llm import (
    LlamaCli,
    NO_EVIDENCE,
    NO_DOCUMENT_ANSWER,
    answer_from_knowledge,
)
from search.knowledge_search import match_event


class FakeGenerator:
    def __init__(self, answer="문서에 따라 DB 연결 포트를 확인하세요."):
        self.answer = answer
        self.calls = []

    def generate(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.answer


class GroundedAnswerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "sources"
        self.db = Path(self.temp.name) / "knowledge.db"
        (self.root / "app-one" / "manuals").mkdir(parents=True)
        (self.root / "app-two" / "manuals").mkdir(parents=True)
        a = self.root / "app-one" / "manuals" / "setup.md"
        a.write_text("# DB 설정\n\n연결 오류 발생 시 포트 3308을 확인합니다.", encoding="utf-8")
        a.with_name(a.name + ".meta.json").write_text(
            '{"document_id":"db-guide","version_from":"2.0","version_to":"3.0"}', encoding="utf-8"
        )
        (self.root / "app-two" / "manuals" / "other.txt").write_text(
            "연결 오류 발생 시 포트 9999 확인", encoding="utf-8"
        )
        build(self.root, self.db)

    def test_grounded_answer_preserves_sources_and_version(self):
        fake = FakeGenerator()
        answer = answer_from_knowledge(
            self.db, product_id="app-one", version="2.5", question="연결 오류 발생 포트는?",
            generator=fake,
        )
        self.assertTrue(answer["grounded"])
        self.assertEqual(len(answer["sources"]), 1)
        self.assertEqual(answer["sources"][0]["document_id"], "db-guide")
        self.assertEqual(answer["sources"][0]["source_path"], "app-one/manuals/setup.md")
        self.assertIn("3308", fake.calls[0][1])
        self.assertNotIn("9999", fake.calls[0][1])
        self.assertIn("매뉴얼:", fake.calls[0][1])
        self.assertIn("매뉴얼 내용만 사용하세요", fake.calls[0][0])
        self.assertIn("정확한 코드·포트·버전·파일명", fake.calls[0][0])
        self.assertGreaterEqual(answer["elapsed_seconds"], 0)

    def test_multi_step_prompt_keeps_numbered_sources_and_bounded_context(self):
        source = self.root / "app-one" / "manuals"
        for n in range(5):
            (source / f"case{n}.md").write_text(
                "연결 오류 해결 절차: " + ("포트 3308을 점검합니다. " * 80),
                encoding="utf-8",
            )
        build(self.root, self.db, rebuild=True)
        fake = FakeGenerator("1. 포트를 확인합니다. [1]")
        result = answer_from_knowledge(
            self.db, product_id="app-one", version="2.5",
            question="연결 오류 해결 절차는?", generator=fake,
        )
        self.assertTrue(result["grounded"])
        self.assertGreaterEqual(len(result["sources"]), 2)
        self.assertLessEqual(len(result["sources"]), 5)
        self.assertIn("[1]", fake.calls[0][1])
        self.assertIn("최대 5단계", fake.calls[0][0])
        self.assertLess(len(fake.calls[0][1]), 5300)

    def test_empty_evidence_never_calls_model(self):
        fake = FakeGenerator()
        no_result = answer_from_knowledge(
            self.db, product_id="app-one", version="1.0", question="포트", generator=fake,
        )
        self.assertEqual(no_result, {"answer": NO_EVIDENCE, "grounded": False, "sources": []})
        self.assertEqual(fake.calls, [])
        unknown = answer_from_knowledge(
            self.db, product_id="app-one", version="2.5", question="배터리절전", generator=fake,
        )
        self.assertFalse(unknown["grounded"])
        self.assertEqual(fake.calls, [])

    def test_cross_product_boundary(self):
        fake = FakeGenerator()
        answer = answer_from_knowledge(
            self.db, product_id="app-two", question="연결 오류 발생", generator=fake,
        )
        self.assertNotEqual(answer["sources"][0]["document_id"], "db-guide")
        self.assertIn("9999", fake.calls[0][1])
        self.assertNotIn("3308", fake.calls[0][1])

    def test_no_document_answer_marks_ungrounded(self):
        fake = FakeGenerator(NO_DOCUMENT_ANSWER)
        answer = answer_from_knowledge(
            self.db, product_id="app-one", version="2.5", question="연결", generator=fake,
        )
        self.assertFalse(answer["grounded"])
        self.assertEqual(len(answer["sources"]), 1)

    def test_invalid_request_does_not_call_llm(self):
        fake = FakeGenerator()
        with self.assertRaises(ValueError):
            answer_from_knowledge(self.db, product_id="app-one", question="", generator=fake)
        with self.assertRaises(ValueError):
            answer_from_knowledge(self.db, product_id="app-one", question="연결", version="v1-beta", generator=fake)
        self.assertEqual(fake.calls, [])

    def test_model_failure_not_falsified_as_answer(self):
        class Broken:
            def generate(self, system, user):
                raise RuntimeError("model not available")
        with self.assertRaisesRegex(RuntimeError, "model not available"):
            answer_from_knowledge(
                self.db, product_id="app-one", version="2.5", question="연결", generator=Broken()
            )

    def test_rules_remain_separate_from_llm(self):
        self.assertEqual(match_event(self.db, product_id="app-one", error_code="DB-1001"), {"matched": False})


class LlamaCliTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.executable = Path(temp.name) / "llama-cli.exe"
        self.model = Path(temp.name) / "qwen.gguf"
        self.executable.write_bytes(b"dummy")
        self.model.write_bytes(b"dummy")

    def test_local_cpu_flags_and_single_turn(self):
        cli = LlamaCli(self.executable, self.model, threads=2, ctx_size=2048, max_tokens=64)
        with patch("llm.local_llm.subprocess.run", return_value=SimpleNamespace(
            returncode=0, stdout="\x1b[32m<think>discard</think>포트를 확인합니다.\x1b[0m", stderr=""
        )) as run:
            result = cli.generate("system text", "user text")
        self.assertEqual(result, "포트를 확인합니다.")
        argv = run.call_args.args[0]
        self.assertIn("--single-turn", argv)
        self.assertIn("--reasoning", argv)
        self.assertIn("--jinja", argv)
        self.assertEqual(argv[argv.index("--reasoning") + 1], "off")
        self.assertEqual(argv[argv.index("-ngl") + 1], "0")
        self.assertEqual(argv[argv.index("-m") + 1], str(self.model.resolve()))
        self.assertEqual(argv[argv.index("-p") + 1], "user text")
        self.assertFalse(run.call_args.kwargs.get("shell", False))
        self.assertEqual(run.call_args.kwargs["timeout"], 180)

    def test_orphan_think_end_tag_removed(self):
        cli = LlamaCli(self.executable, self.model, prompt_mode="raw_chatml")
        with patch("llm.local_llm.subprocess.run", return_value=SimpleNamespace(
            returncode=0, stdout="</think>\\n\\n설치 확인 코드는 DKTEST-3308입니다. [1]", stderr=""
        )):
            self.assertEqual(cli.generate("system", "user"), "설치 확인 코드는 DKTEST-3308입니다. [1]")

    def test_completion_end_marker_removed(self):
        cli = LlamaCli(self.executable, self.model)
        with patch("llm.local_llm.subprocess.run", return_value=SimpleNamespace(
            returncode=0, stdout="제공된 근거 문서만으로는 답변을 확인할 수 없습니다. [end of text]", stderr=""
        )):
            self.assertEqual(cli.generate("system", "user"), NO_DOCUMENT_ANSWER)

    def test_runtime_exit_code_is_an_error(self):
        cli = LlamaCli(self.executable, self.model)
        with patch("llm.local_llm.subprocess.run", return_value=SimpleNamespace(
            returncode=2, stdout="", stderr="model loading failure"
        )):
            with self.assertRaisesRegex(RuntimeError, "exit code 2"):
                cli.generate("system", "user")

    def test_empty_or_unfinished_thought_rejected(self):
        cli = LlamaCli(self.executable, self.model)
        with patch("llm.local_llm.subprocess.run", return_value=SimpleNamespace(
            returncode=0, stdout="<think>unfinished", stderr=""
        )):
            with self.assertRaisesRegex(RuntimeError, "no visible answer"):
                cli.generate("system", "user")

    def test_console_transcript_is_rejected(self):
        cli = LlamaCli(self.executable, self.model)
        with patch("llm.local_llm.subprocess.run", return_value=SimpleNamespace(
            returncode=0, stdout="Loading model... <references> 포트 3308 Exiting...", stderr=""
        )):
            with self.assertRaisesRegex(RuntimeError, "console transcript"):
                cli.generate("system", "user")

    def test_missing_files_rejected_before_subprocess(self):
        with self.assertRaises(FileNotFoundError):
            LlamaCli("does-not-exist.exe", self.model)
        with self.assertRaises(ValueError):
            LlamaCli(self.executable, self.model, threads=0)


if __name__ == "__main__":
    unittest.main()
