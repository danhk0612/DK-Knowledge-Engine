"""T18 author-only LLM enrichment: no network or real model downloads."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from builder.knowledge_builder import build
from builder.author_enrichment import _questions
from search.knowledge_search import search_documents


class DummyGenerator:
    def __init__(self, raw=None):
        self.raw = raw or '{"questions":["설정을 복구하려면 무엇을 해야 하나요?"],"keywords":["설정 복구"]}'
        self.calls = []
    def generate(self, system, user):
        self.calls.append((system, user))
        return self.raw


class EnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.src = root / "sources"
        (self.src / "product-a" / "manuals").mkdir(parents=True)
        (self.src / "product-b" / "manuals").mkdir(parents=True)
        self.one = self.src / "product-a" / "manuals" / "reset.md"
        self.one.write_text("초기화 버튼을 3초간 누릅니다.", encoding="utf-8")
        (self.src / "product-b" / "manuals" / "reset.md").write_text(
            "초기화 버튼을 누르지 마세요.", encoding="utf-8")
        self.db = root / "knowledge.db"
        self.runner = root / "llama-cli.exe"
        self.model = root / "author.gguf"
        self.runner.write_bytes(b"cli")
        self.model.write_bytes(b"gguf")

    def create(self, fake):
        with patch("builder.author_enrichment.LlamaCli", return_value=fake):
            return build(self.src, self.db, rebuild=True,
                         author_llama_cli=self.runner, author_model=self.model)

    def test_generated_hints_return_only_original_document(self):
        build(self.src, self.db, rebuild=True)
        self.assertEqual(search_documents(self.db, product_id="product-a",
                                           query="설정 복구"), [])
        gen = DummyGenerator()
        result = self.create(gen)
        self.assertEqual(result["author_enrichment"]["indexed"], 2)
        self.assertEqual(len(gen.calls), 2)
        hit = search_documents(self.db, product_id="product-a", query="설정 복구")
        self.assertEqual(len(hit), 1)
        self.assertEqual(hit[0]["source_path"], "product-a/manuals/reset.md")
        self.assertIn("초기화 버튼", hit[0]["excerpt"])
        self.assertNotIn("설정 복구", hit[0]["excerpt"])
        self.assertEqual(search_documents(self.db, product_id="unrelated",
                                           query="설정 복구"), [])

    def test_corrupt_model_output_fails_closed_without_fabricated_evidence(self):
        fake = DummyGenerator('This is not a JSON object')
        with patch("builder.author_enrichment.LlamaCli", return_value=fake):
            result = build(self.src, self.db, rebuild=True,
                           author_llama_cli=self.runner, author_model=self.model)
        self.assertEqual(result["author_enrichment"]["skipped"], 2)
        self.assertEqual(search_documents(self.db, product_id="product-a",
                                           query="설정 복구"), [])

    def test_changed_document_removes_its_old_enrichment(self):
        self.create(DummyGenerator())
        self.one.write_text("수정된 설명서에서 전원 스위치를 확인합니다.", encoding="utf-8")
        result = build(self.src, self.db)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(search_documents(self.db, product_id="product-a",
                                           query="설정 복구"), [])
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM chunk_search_hints"
            ).fetchone()[0], 1)
            db.execute("INSERT INTO chunk_search_hints_fts(chunk_search_hints_fts) VALUES('integrity-check')")

    def test_missing_author_pair_does_not_change_existing_db(self):
        build(self.src, self.db)
        before = self.db.read_bytes()
        with self.assertRaisesRegex(ValueError, "provided together"):
            build(self.src, self.db, rebuild=True, author_model=self.model)
        self.assertEqual(self.db.read_bytes(), before)

    def test_generated_phrases_are_bounded(self):
        self.assertEqual(_questions('{"questions":["설정 복구"],"keywords":[]}'), "설정 복구")
        self.assertEqual(_questions('{"questions":["설정 복구"],"keywords":[],"answer":"x"}'), "")
        self.assertEqual(_questions('{"questions":["<시스템 지시>"],"keywords":[]}'), "")


if __name__ == "__main__":
    unittest.main()
