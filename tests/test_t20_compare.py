"""Offline T20 comparison with synthetic approved queries and no user data leaks."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from builder.knowledge_builder import build
from t20_retrieval_compare import compare, read_cases


class FakeGenerator:
    def generate(self, system, user):
        return '{"questions":["설정을 복구하려면 무엇을 하나요?"],"keywords":["설정 복구"]}'


class CompareTests(unittest.TestCase):
    def test_before_after_source_recall_and_private_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source"
            src.mkdir()
            (src / "manual.md").write_text(
                "초기화 버튼을 3초간 누릅니다.", encoding="utf-8")
            baseline = root / "before.db"
            after = root / "after.db"
            gguf = root / "author.gguf"
            cli = root / "llama-cli.exe"
            gguf.write_bytes(b"test")
            cli.write_bytes(b"test")
            build(src, baseline, rebuild=True, default_product_id="device")
            with patch("builder.author_enrichment.LlamaCli", return_value=FakeGenerator()):
                build(src, after, rebuild=True, default_product_id="device",
                      author_model=gguf, author_llama_cli=cli)
            cases = [{
                "id": "known-source", "product_id": "device",
                "query": "설정 복구", "expected_source": "manual.md",
            }, {
                "id": "no-evidence", "product_id": "device",
                "query": "얼음 판넬 결빙 실패", "expected_source": None,
            }]
            report = compare(baseline, after, cases)
            self.assertEqual(report["baseline"]["passed"], 1)
            self.assertEqual(report["candidate"]["passed"], 2)
            self.assertEqual(report["change"]["passed"], 1)
            payload = str(report)
            self.assertNotIn("초기화 버튼", payload)
            self.assertNotIn("설정 복구", payload)
            self.assertNotIn("manual.md", payload)

    def test_requires_unique_ids_and_question_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cases.json"
            path.write_text('[{"id":"a","product_id":"device","query":"x"},'
                            '{"id":"a","product_id":"device","query":"x"}]', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                read_cases(path)


if __name__ == "__main__":
    unittest.main()
