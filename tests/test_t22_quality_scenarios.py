"""Six synthetic Korean manual scenarios, independent of any customer PDF."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from builder.knowledge_builder import build
from llm.local_llm import NO_DOCUMENT_ANSWER, answer_from_knowledge
from search.knowledge_search import search_documents


class QualityScenarioTests(unittest.TestCase):
    def test_six_document_questions_and_absent_gpu_fact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "manuals"
            root.mkdir()
            passages = {
                "comparison.md": (
                    "회로시험은 실제 수신기 출력과 경고음이 동작할 수 있습니다. "
                    "시뮬레이션은 감지기의 연동 동작을 보여주지만 실제 수신기 출력은 나가지 않습니다."
                ),
                "report.md": "보고서는 XLS 및 PDF 형식으로 다운로드할 수 있습니다.",
                "network.md": "통신장애 발생 시 팝업을 확인한 후 수신기 설정을 점검합니다.",
                "restart.md": (
                    "구역명, 키 상태값, 동기화, 글자 입력 문제가 발생하면 "
                    "프로그램 재기동을 확인합니다."
                ),
                "permission.md": (
                    "기능      관리자        일반사용자\n"
                    "기록조회     O             O\n"
                    "회로시험     O             X"
                ),
            }
            for filename, passage in passages.items():
                (root / filename).write_text(passage, encoding="utf-8")
            database = Path(temporary) / "knowledge.db"
            build(root, database, default_product_id="synthetic", rebuild=True)

            questions = {
                "회로시험과 시뮬레이션의 차이는?": "comparison.md",
                "XLS/PDF 다운로드 가능한가요?": "report.md",
                "통신장애가 발생하면 어떻게 확인해야 하나요?": "network.md",
                "프로그램을 재기동해야 하는 경우는?": "restart.md",
                "일반사용자가 회로시험 가능한가요?": "permission.md",
            }
            for question, filename in questions.items():
                with self.subTest(question=question):
                    hits = search_documents(
                        database, product_id="synthetic", query=question, limit=5,
                    )
                    self.assertTrue(hits)
                    self.assertEqual(hits[0]["source_path"], filename)

            self.assertEqual(
                search_documents(
                    database, product_id="synthetic",
                    query="최소 GPU VRAM 메모리 용량은?",
                ),
                [],
            )

            class Generated:
                def __init__(self, value):
                    self.value = value

                def generate(self, system, user):
                    return self.value

            generated = Generated("일반사용자는 회로시험이 가능합니다. [1]")
            denied = answer_from_knowledge(
                database, product_id="synthetic",
                question="일반사용자가 회로시험 가능한가요?", generator=generated,
            )
            self.assertFalse(denied["grounded"])
            self.assertEqual(denied["answer"], NO_DOCUMENT_ANSWER)

            generated.value = "일반사용자는 회로시험을 할 수 없습니다. [1]"
            correct = answer_from_knowledge(
                database, product_id="synthetic",
                question="일반사용자가 회로시험 가능한가요?", generator=generated,
            )
            self.assertTrue(correct["grounded"])


if __name__ == "__main__":
    unittest.main()
