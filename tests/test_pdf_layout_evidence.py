"""Synthetic PDF layout regression: table permissions and split-page comparisons.

The generated fixture contains no customer manual text or assets.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from reportlab.pdfgen.canvas import Canvas

from builder.knowledge_builder import build
from llm.local_llm import NO_DOCUMENT_ANSWER, answer_from_knowledge
from search.knowledge_search import search_documents


class _Answer:
    def __init__(self, value: str) -> None:
        self.value = value

    def generate(self, system: str, user: str) -> str:
        return self.value


class PdfLayoutEvidenceTests(unittest.TestCase):
    def test_generated_pdf_table_and_split_pages_reach_client_grounding(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            docs = folder / "sources"
            docs.mkdir()
            pdf = docs / "synthetic-guide.pdf"
            canvas = Canvas(str(pdf), pagesize=(612, 792))
            canvas.setFont("Helvetica", 12)

            # Page 1: draw independently positioned text cells, not a
            # preformatted text paragraph. Layout extraction must reconstruct
            # the row/column relationship for permission checking.
            for label, x in (("Feature", 40), ("Admin", 260), ("User", 410)):
                canvas.drawString(x, 740, label)
            for label, x in (("Settings", 40), ("O", 260), ("X", 410)):
                canvas.drawString(x, 692, label)
            for label, x in (("Read", 40), ("O", 260), ("O", 410)):
                canvas.drawString(x, 644, label)
            canvas.drawString(40, 560, "Contents: CircuitTest 2 / Simulation 3")
            canvas.showPage()

            # Two explanatory pages: each has one comparison subject. The
            # contents/index page above mentions both but is not evidence.
            canvas.setFont("Helvetica", 12)
            canvas.drawString(40, 700, "CircuitTest sends real output signals.")
            canvas.showPage()
            canvas.setFont("Helvetica", 12)
            canvas.drawString(40, 700, "Simulation does not send real output signals.")
            canvas.save()

            db = folder / "knowledge.db"
            build(docs, db, default_product_id="test-program",
                  pdf_layout=True, rebuild=True)

            permission_question = "User Settings 가능한가요?"
            hits = search_documents(db, product_id="test-program",
                                    query=permission_question)
            self.assertTrue(hits)
            self.assertEqual(hits[0]["page_from"], 1)
            self.assertIn("Settings", hits[0]["excerpt"])
            self.assertIn("User", hits[0]["excerpt"])

            fake = _Answer("User는 Settings를 할 수 있습니다. [1]")
            rejected = answer_from_knowledge(
                db, product_id="test-program",
                question=permission_question, generator=fake,
            )
            self.assertFalse(rejected["grounded"])
            self.assertEqual(rejected["answer"], NO_DOCUMENT_ANSWER)

            fake.value = "User는 Settings를 할 수 없습니다. [1]"
            allowed = answer_from_knowledge(
                db, product_id="test-program",
                question=permission_question, generator=fake,
            )
            self.assertTrue(allowed["grounded"])

            compare_question = "CircuitTest와 Simulation의 차이는?"
            comparison_hits = search_documents(
                db, product_id="test-program", query=compare_question,
            )
            self.assertGreaterEqual(len(comparison_hits), 2)
            self.assertEqual(
                [hit["page_from"] for hit in comparison_hits[:2]], [2, 3],
            )

            fake.value = (
                "CircuitTest는 실제 신호를 보내지만 Simulation은 보내지 않습니다. "
                "[1] [2]"
            )
            comparison = answer_from_knowledge(
                db, product_id="test-program",
                question=compare_question, generator=fake,
            )
            self.assertTrue(comparison["grounded"])
            self.assertEqual(
                [source["page_from"] for source in comparison["sources"][:2]], [2, 3],
            )


if __name__ == "__main__":
    unittest.main()
