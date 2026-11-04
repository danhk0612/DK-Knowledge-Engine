"""T03 search regression tests using a T02-compatible SQLite fixture."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from search.knowledge_search import match_event, search_documents

SCHEMA = """
CREATE TABLE schema_info (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE documents (
 document_id TEXT PRIMARY KEY, product_id TEXT NOT NULL, title TEXT NOT NULL,
 source_path TEXT NOT NULL UNIQUE, source_type TEXT NOT NULL,
 version_from TEXT, version_to TEXT, language TEXT,
 source_hash TEXT NOT NULL, metadata_hash TEXT NOT NULL
);
CREATE TABLE chunks (
 id INTEGER PRIMARY KEY, chunk_id TEXT NOT NULL UNIQUE,
 document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
 section_title TEXT, content TEXT NOT NULL, page_from INTEGER, page_to INTEGER,
 sequence INTEGER NOT NULL, UNIQUE(document_id, sequence)
);
CREATE VIRTUAL TABLE chunks_fts USING fts5(
 section_title, content, content='chunks', content_rowid='id', tokenize='unicode61'
);
CREATE TABLE help_rules (
 rule_id TEXT PRIMARY KEY, product_id TEXT NOT NULL,
 event_id TEXT, error_code TEXT, screen_id TEXT,
 version_from TEXT, version_to TEXT,
 document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
 chunk_id TEXT REFERENCES chunks(chunk_id),
 title TEXT NOT NULL, content TEXT NOT NULL, source_path TEXT NOT NULL
);
"""


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "knowledge.db"
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript(SCHEMA)
            db.execute("INSERT INTO schema_info VALUES ('schema_version', '1')")

    def doc(self, doc_id, product="app-a", start=None, end=None,
            text="설치 오류 해결 안내", title="Manual", page=2):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (doc_id, product, title, f"{product}/manuals/{doc_id}.md",
                        "md", start, end, "ko", "sha", "meta"))
            cur = db.execute("""INSERT INTO chunks
                (chunk_id, document_id, section_title, content, page_from, page_to, sequence)
                VALUES (?,?,?,?,?,?,?)""",
                (f"{doc_id}:000001", doc_id, "Troubleshooting", text, page, page, 1))
            db.execute("INSERT INTO chunks_fts(rowid, section_title, content) VALUES (?,?,?)",
                       (cur.lastrowid, "Troubleshooting", text))

    def rule(self, rule_id, doc_id, *, event=None, error=None, screen=None,
             start=None, end=None):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("INSERT INTO help_rules VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                       (rule_id, "app-a", event, error, screen, start, end,
                        doc_id, f"{doc_id}:000001", "도움말", f"조치 {rule_id}",
                        f"app-a/rules/{rule_id}.json"))

    def docs(self, query, **kwargs):
        return search_documents(self.path, product_id="app-a", query=query, **kwargs)

    def test_product_filter_and_provenance(self):
        self.doc("a", product="app-a", text="Database connection failed", page=12)
        self.doc("b", product="app-b", text="Database connection failed")
        hits = self.docs("Database")
        self.assertEqual([h["document_id"] for h in hits], ["a"])
        self.assertEqual(hits[0]["source_path"], "app-a/manuals/a.md")
        self.assertEqual(hits[0]["page_from"], 12)

    def test_numeric_version_order_and_inclusive_bounds(self):
        self.doc("old", start="1.0", end="2.9", text="Important version")
        self.doc("new", start="2.10", end="3.0.0", text="Important version")
        self.assertEqual([x["document_id"] for x in self.docs("Important", version="2.9")], ["old"])
        self.assertEqual([x["document_id"] for x in self.docs("Important", version="2.10")], ["new"])
        self.assertEqual([x["document_id"] for x in self.docs("Important", version="3.0")], ["new"])
        self.assertEqual(self.docs("Important", version="3.1"), [])

    def test_missing_unsupported_or_reversed_version_fails_closed(self):
        self.doc("bounded", start="2.0", text="Alpha version")
        self.doc("unbounded", text="Alpha always")
        self.assertEqual([x["document_id"] for x in self.docs("Alpha")], ["unbounded"])
        with self.assertRaisesRegex(ValueError, "Unsupported version"):
            self.docs("Alpha", version="v2.0-beta")
        self.doc("bad", start="v2", text="Alpha invalid")
        self.doc("backwards", start="3.0", end="2.0", text="Alpha reversed")
        ids = [x["document_id"] for x in self.docs("Alpha", version="2.0")]
        self.assertNotIn("bad", ids)
        self.assertNotIn("backwards", ids)

    def test_fts_user_syntax_is_not_executed(self):
        self.doc("a", text='DB-1001: "network" failure')
        self.assertEqual(len(self.docs('DB-1001 "network"')), 1)
        self.assertEqual(len(self.docs('network OR failure')), 1)
        self.assertEqual(self.docs("!#$"), [])
        self.assertEqual(self.docs(""), [])

    def test_korean_unicode61_token_limit(self):
        self.doc("a", text="데이터베이스 연결 실패를 확인합니다")
        self.assertEqual(len(self.docs("연결")), 1)
        self.assertEqual(self.docs("실패"), [])
        self.assertEqual(len(self.docs("실패를")), 1)

    def test_updated_and_removed_fts_data(self):
        self.doc("a", text="oldtoken")
        self.assertEqual(len(self.docs("oldtoken")), 1)
        with closing(sqlite3.connect(self.path)) as db:
            rowid = db.execute("SELECT id FROM chunks WHERE chunk_id='a:000001'").fetchone()[0]
            db.execute("""INSERT INTO chunks_fts(chunks_fts, rowid, section_title, content)
                          VALUES ('delete', ?, ?, ?)""", (rowid, "Troubleshooting", "oldtoken"))
            db.execute("UPDATE chunks SET content='newtoken' WHERE id=?", (rowid,))
            db.execute("INSERT INTO chunks_fts(rowid, section_title, content) VALUES (?,?,?)",
                       (rowid, "Troubleshooting", "newtoken"))
        self.assertEqual(self.docs("oldtoken"), [])
        self.assertEqual(len(self.docs("newtoken")), 1)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("DELETE FROM chunks_fts WHERE rowid=?", (rowid,))
            db.execute("DELETE FROM chunks WHERE id=?", (rowid,))
        self.assertEqual(self.docs("newtoken"), [])

    def test_exact_event_and_broad_fallback(self):
        self.doc("guide")
        self.rule("generic", "guide", error="DB-1001")
        self.rule("exact", "guide", event="connection_failed",
                  error="DB-1001", screen="connection_screen")
        res = match_event(self.path, product_id="app-a", version="2.0",
                          event_id="connection_failed", error_code="DB-1001",
                          screen_id="connection_screen")
        self.assertEqual(res["rule_id"], "exact")
        self.assertEqual(res["source"]["document_id"], "guide")
        self.assertEqual(match_event(self.path, product_id="app-a",
                                     error_code="DB-1001")["rule_id"], "generic")
        self.assertEqual(match_event(self.path, product_id="app-b", error_code="DB-1001"),
                         {"matched": False})

    def test_event_version_fallback_and_document_version(self):
        self.doc("guide", start="2.0", end="3.0")
        self.rule("generic", "guide", error="E1")
        self.rule("bounded", "guide", error="E1", start="2.10", end="2.12")
        self.assertEqual(match_event(self.path, product_id="app-a",
                                     version="2.9", error_code="E1")["rule_id"], "generic")
        self.assertEqual(match_event(self.path, product_id="app-a",
                                     version="2.10", error_code="E1")["rule_id"], "bounded")
        self.assertEqual(match_event(self.path, product_id="app-a",
                                     version="3.1", error_code="E1"), {"matched": False})
        self.assertEqual(match_event(self.path, product_id="app-a",
                                     error_code="E1"), {"matched": False})

    def test_equal_priority_rule_collision(self):
        self.doc("guide")
        self.rule("r1", "guide", error="DB-1001")
        self.rule("r2", "guide", error="DB-1001")
        self.assertEqual(match_event(self.path, product_id="app-a", error_code="DB-1001"),
                         {"matched": False, "reason": "ambiguous_rules"})

    def test_event_requires_identifier_and_valid_version(self):
        with self.assertRaisesRegex(ValueError, "event_id or error_code"):
            match_event(self.path, product_id="app-a")
        with self.assertRaisesRegex(ValueError, "Unsupported version"):
            match_event(self.path, product_id="app-a", error_code="x", version="1.0-rc1")

    def test_missing_database_and_input_validation(self):
        self.doc("a", text="hello world")
        with self.assertRaisesRegex(ValueError, "limit"):
            self.docs("hello", limit=0)
        with self.assertRaisesRegex(ValueError, "product_id"):
            search_documents(self.path, product_id="", query="hello")
        with self.assertRaises(FileNotFoundError):
            search_documents(self.path.parent / "missing.db", product_id="app-a", query="x")
        self.assertEqual(len(self.docs("hello")), 1)

    def test_wrong_database_schema(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("UPDATE schema_info SET value='2' WHERE key='schema_version'")
        with self.assertRaisesRegex(ValueError, "schema version"):
            self.docs("hello")


if __name__ == "__main__":
    unittest.main()
