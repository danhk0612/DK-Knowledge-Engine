"""T10 evaluator tests with the real localhost API and synthetic ground truth."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from api.localhost_api import KnowledgeHttpServer
from t10_eval import evaluate, evaluate_case, read_cases
from t10_fixture import produce


class SyntheticGenerator:
    def generate(self, system: str, user: str) -> str:
        # This exercises the evaluator's HTTP/retrieval provenance checks,
        # not a claim of real LLM answer quality.
        return "데이터베이스 연결 포트 9999를 확인하세요." if "9999" in user else (
            "데이터베이스 연결 포트 3308을 확인하세요."
        )


class T10EvaluatorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.db = self.root / "knowledge.db"
        produce(self.db)
        cases_path = Path(__file__).with_name("t10_cases_sample.json")
        self.cases = read_cases(cases_path)
        self.server = KnowledgeHttpServer(
            self.db, port=0, generator=SyntheticGenerator()
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.addCleanup(self.shutdown)

    def shutdown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @property
    def port(self):
        return self.server.server_port

    def test_all_synthetic_cases_and_http_boundaries(self):
        result = evaluate(self.db, self.cases, self.port)
        self.assertEqual(result["cases_count"], 14)
        self.assertEqual(result["failed_count"], 0, result["results"])
        self.assertEqual(result["cases_by_kind"]["http-security"], 4)
        self.assertEqual(result["cases_by_kind"]["chat"], 4)
        self.assertEqual(result["cases_by_kind"]["search"], 3)

    def test_report_excludes_question_answers_and_source_paths(self):
        report = json.dumps(evaluate(self.db, self.cases, self.port), ensure_ascii=False)
        self.assertNotIn("연결 오류가 발생하면", report)
        self.assertNotIn("데이터베이스 연결 포트", report)
        self.assertNotIn("product-alpha/manuals/", report)
        self.assertIn("knowledge_sha256", report)

    def test_detects_model_answer_that_contradicts_evidence(self):
        case = next(x for x in self.cases if x["id"] == "alpha-grounded-chat")
        with patch("t10_eval.request", return_value=(200, {
            "grounded": True,
            "answer": "연결 오류 시 포트 9999를 확인하세요.",
            "sources": [
                {"document_id": "alpha-db", "chunk_id": "dummy",
                 "source_path": "product-alpha/manuals/database.md",
                 "page_from": None},
            ],
        }, {})):
            result = evaluate_case(self.db, self.port, case)
        self.assertFalse(result["passed"])
        self.assertIn("forbidden-text-present", result["failures"])
        self.assertIn("citation-not-in-requested-retrieval", result["failures"])

    def test_detects_wrong_product_source(self):
        case = next(x for x in self.cases if x["id"] == "alpha-grounded-chat")
        with patch("t10_eval.request", return_value=(200, {
            "grounded": True, "answer": "3308",
            "sources": [
                {"document_id": "beta-db", "chunk_id": "beta-chunk",
                 "source_path": "product-beta/manuals/database.md",
                 "page_from": None}
            ],
        }, {})):
            result = evaluate_case(self.db, self.port, case)
        self.assertFalse(result["passed"])
        self.assertIn("citation-not-in-requested-retrieval", result["failures"])
        self.assertIn("expected-source-missing", result["failures"])

    def test_invalid_or_duplicate_gold_cases_rejected(self):
        case = self.cases[0]
        target = self.root / "bad-cases.json"
        target.write_text(json.dumps([case, case]), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unique"):
            read_cases(target)
        target.write_text(json.dumps([{
            "id": "without-ground-truth", "kind": "chat",
            "product_id": "product-alpha", "question": "포트?",
            "expected_grounded": True,
        }]), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "expected_any"):
            read_cases(target)


if __name__ == "__main__":
    unittest.main()
