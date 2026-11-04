"""T02 regression tests with generated, non-copyrighted sample documents."""

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from builder.knowledge_builder import build, _make_chunks, Segment


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "sources"
        self.out = Path(self.temp.name) / "knowledge.db"
        (self.root / "product-one" / "manuals").mkdir(parents=True)
        (self.root / "product-two" / "manuals").mkdir(parents=True)

    def put(self, relative, text):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def db(self):
        db = sqlite3.connect(self.out)
        db.row_factory = sqlite3.Row
        self.addCleanup(db.close)
        return db

    def snapshot(self, db):
        return {
            name: [tuple(row) for row in db.execute("SELECT * FROM " + name + " ORDER BY 1")]
            for name in ("documents", "chunks", "help_rules")
        }

    def assert_fts(self, db, query, count):
        self.assertEqual(db.execute("SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?", (query,)).fetchone()[0], count)
        db.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('integrity-check')")

    def test_all_formats_provenance_and_original_unchanged(self):
        from docx import Document
        from reportlab.pdfgen import canvas
        md = self.put("product-one/manuals/setup.md", "# 연결 설정\n\nDB 서버 실행 상태를 확인합니다.\n\n## 연결 오류\n\nDB-1001 코드를 확인하세요.")
        txt = self.put("product-one/manuals/config.txt", "Connection parameters\n\nPort 3306 is default.")
        docx = self.root / "product-one/manuals/guide.docx"
        document = Document()
        document.add_heading("Network Setup", 1)
        document.add_paragraph("Check firewall settings.")
        table = document.add_table(rows=1, cols=2)
        table.cell(0, 0).text = "Hostname"
        table.cell(0, 1).text = "localhost"
        document.save(docx)
        pdf = self.root / "product-one/manuals/reference.pdf"
        c = canvas.Canvas(str(pdf))
        c.drawString(60, 700, "Database settings for the application")
        c.showPage()
        c.drawString(60, 700, "Resolve authentication error")
        c.save()
        originals = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in [md, txt, docx, pdf]}
        result = build(self.root, self.out)
        self.assertEqual(result["added"], 4)
        self.assertEqual(result["chunks"], 6)  # MD 2, TXT 1, DOCX 1, PDF 2
        self.assertFalse(result["warnings"])
        with self.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 4)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM chunks WHERE page_from IS NOT NULL").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM chunks WHERE section_title='Network Setup'").fetchone()[0], 1)
            self.assert_fts(db, "authentication", 1)
            self.assert_fts(db, '"연결"', 2)
            self.assertEqual(db.execute("SELECT value FROM schema_info WHERE key='schema_version'").fetchone()[0], "1")
        self.assertEqual({p: hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}, originals)

    def test_update_add_delete_no_stale_index_and_stable_id(self):
        first = self.put("product-one/manuals/a.md", "# Old\n\ninitialkeyword")
        second = self.put("product-two/manuals/b.txt", "otherproduct")
        first_result = build(self.root, self.out)
        self.assertEqual(first_result["added"], 2)
        with self.db() as db:
            original_id = db.execute("SELECT document_id FROM documents WHERE source_path=?", ("product-one/manuals/a.md",)).fetchone()[0]
        self.assertEqual(build(self.root, self.out)["unchanged"], 2)
        self.assertEqual(build(self.root, self.out)["added"], 0)
        first.write_text("# New\n\nrevisedkeyword", encoding="utf-8")
        third = self.put("product-one/manuals/c.txt", "thirdkeyword")
        second.unlink()
        updated = build(self.root, self.out)
        self.assertEqual([updated[k] for k in ("added", "updated", "deleted")], [1, 1, 1])
        with self.db() as db:
            self.assertEqual(original_id, db.execute("SELECT document_id FROM documents WHERE source_path=?", ("product-one/manuals/a.md",)).fetchone()[0])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 2)
            self.assert_fts(db, "initialkeyword", 0)
            self.assert_fts(db, "otherproduct", 0)
            self.assert_fts(db, "revisedkeyword", 1)
            self.assert_fts(db, "thirdkeyword", 1)

    def test_full_rebuild_logical_equivalence(self):
        self.put("product-one/manuals/a.md", "# one\n\nA word")
        self.put("product-two/manuals/b.txt", "B word")
        build(self.root, self.out)
        with self.db() as db:
            incremental = self.snapshot(db)
        rebuild = build(self.root, self.out, rebuild=True)
        self.assertEqual(rebuild["added"], 2)
        with self.db() as db:
            self.assertEqual(incremental, self.snapshot(db))
            self.assert_fts(db, "word", 2)

    def test_rollback_on_invalid_pdf_and_corrupt_rule(self):
        from pypdf import PdfWriter
        self.put("product-one/manuals/a.txt", "original")
        build(self.root, self.out)
        with self.db() as db:
            before = self.snapshot(db)
        blank = self.root / "product-one/manuals/scan.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        with blank.open("wb") as f:
            writer.write(f)
        with self.assertRaisesRegex(ValueError, "No extractable text"):
            build(self.root, self.out)
        blank.unlink()
        self.put("product-one/rules/bad.json", json.dumps({"rule_id": "r1", "product_id": "product-one", "error_code": "E1", "document_id": "wrong", "title": "Error", "content": "Fix"}))
        with self.assertRaisesRegex(ValueError, "cross-product document"):
            build(self.root, self.out)
        with self.db() as db:
            self.assertEqual(before, self.snapshot(db))

    def test_partial_blank_pdf_warning(self):
        from reportlab.pdfgen import canvas
        p = self.root / "product-one/manuals/mixed.pdf"
        c = canvas.Canvas(str(p))
        c.drawString(30, 700, "Working section")
        c.showPage()
        c.showPage()
        c.save()
        result = build(self.root, self.out)
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("page 2", result["warnings"][0])

    def test_metadata_and_rules_references(self):
        doc = self.put("product-one/manuals/guide.md", "# Connection\n\nServer not available")
        sidecar = doc.with_name(doc.name + ".meta.json")
        sidecar.write_text(json.dumps({"document_id": "guide-main", "title": "Main Guide", "version_from": "2.0.0", "language": "ko"}), encoding="utf-8")
        rule = {"rule_id": "db-1", "product_id": "product-one", "event_id": "connection_failed", "error_code": "DB-1001",
                "document_id": "guide-main", "chunk_id": "guide-main:000001", "title": "Connection issue", "content": "Check the port"}
        self.put("product-one/rules/db.json", json.dumps(rule))
        result = build(self.root, self.out)
        self.assertEqual(result["rules"], 1)
        with self.db() as db:
            self.assertEqual(db.execute("SELECT title FROM documents WHERE document_id='guide-main'").fetchone()[0], "Main Guide")
            self.assertEqual(db.execute("SELECT chunk_id FROM help_rules WHERE rule_id='db-1'").fetchone()[0], "guide-main:000001")
        sidecar.write_text(json.dumps({"document_id": "guide-main", "title": "Updated Guide", "version_from": "2.0.0"}), encoding="utf-8")
        result = build(self.root, self.out)
        self.assertEqual(result["updated"], 1)
        rule_file = self.root / "product-one/rules/db.json"
        rule_file.unlink()
        doc.unlink()
        sidecar.unlink()
        result = build(self.root, self.out)
        self.assertEqual((result["deleted"], result["rules"]), (1, 0))

    def test_duplicate_id_rejected(self):
        a = self.put("product-one/manuals/a.md", "A")
        b = self.put("product-one/manuals/b.md", "B")
        for p in (a, b):
            p.with_name(p.name + ".meta.json").write_text('{"document_id":"same"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate document_id"):
            build(self.root, self.out)

    def test_long_paragraph_and_korean_fts_limit(self):
        chunks = _make_chunks([Segment("가" * 2800, "section", None)])
        self.assertEqual(len(chunks), 3)
        self.assertEqual("".join(c["content"] for c in chunks), "가" * 2800)
        self.put("product-one/manuals/a.txt", "연결 실패를 확인합니다")
        build(self.root, self.out)
        with self.db() as db:
            self.assert_fts(db, '"실패"', 0)
            self.assert_fts(db, '"연결"', 1)
            self.assert_fts(db, '"연결 실패를 확인합니다"', 1)

    def test_changed_content_rebuild_matches_incremental_logically(self):
        a = self.put("product-one/manuals/a.md", "# Intro\n\nInitial")
        b = self.put("product-one/manuals/b.txt", "Original")
        build(self.root, self.out)
        a.write_text("# Intro\n\nRevised", encoding="utf-8")
        b.unlink()
        self.put("product-two/manuals/c.md", "# New\n\nAdded")
        build(self.root, self.out)

        def logical_snapshot():
            with sqlite3.connect(self.out) as db:
                documents = db.execute("SELECT document_id, product_id, title, source_path, source_hash FROM documents ORDER BY source_path").fetchall()
                chunks = db.execute("SELECT chunk_id, document_id, section_title, content, page_from, sequence FROM chunks ORDER BY chunk_id").fetchall()
                return documents, chunks

        actual = logical_snapshot()
        build(self.root, self.out, rebuild=True)
        self.assertEqual(actual, logical_snapshot())

    def test_failed_full_rebuild_does_not_replace_existing_database(self):
        self.put("product-one/manuals/a.txt", "Original")
        build(self.root, self.out)
        original_bytes = self.out.read_bytes()
        self.put("product-one/rules/wrong.json", json.dumps({"rule_id": "x", "product_id": "product-one", "event_id": "e", "document_id": "missing", "title": "x", "content": "x"}))
        with self.assertRaises(ValueError):
            build(self.root, self.out, rebuild=True)
        self.assertEqual(self.out.read_bytes(), original_bytes)

    def test_invalid_existing_db_schema_rejected(self):
        with sqlite3.connect(self.out) as db:
            db.execute("CREATE TABLE other (name TEXT)")
        self.put("product-one/manuals/a.txt", "Text")
        with self.assertRaisesRegex(ValueError, "no recognized schema_info"):
            build(self.root, self.out)


if __name__ == "__main__":
    unittest.main()
