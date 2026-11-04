"""T02 Builder -> T03 search integration, using generated sample documents."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from builder.knowledge_builder import build
from search.knowledge_search import match_event, search_documents


class BuilderSearchIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "sources"
        self.db = Path(self.temp.name) / "knowledge.db"
        (self.root / "app-a" / "manuals").mkdir(parents=True)
        (self.root / "app-b" / "manuals").mkdir(parents=True)

    def write(self, relative, content):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def test_builder_metadata_events_and_incremental_updates(self):
        a = self.write("app-a/manuals/setup.md",
                       "# 데이터베이스\n\nDB-1001 연결 실패. 서버 포트를 확인하세요.")
        self.write("app-a/manuals/setup.md.meta.json", json.dumps({
            "document_id": "setup-a", "version_from": "2.10.0", "version_to": "3.0.0"
        }))
        self.write("app-b/manuals/other.md", "# DB-1001\n\n서버 포트 확인하세요.")
        self.write("app-a/rules/db.json", json.dumps({
            "rule_id": "db-1001", "product_id": "app-a", "event_id": "connection_failed",
            "error_code": "DB-1001", "document_id": "setup-a", "chunk_id": None,
            "title": "연결 실패", "content": "포트를 확인하세요."
        }))
        self.assertEqual(build(self.root, self.db)["added"], 2)
        hits = search_documents(self.db, product_id="app-a", version="2.10", query="서버")
        self.assertEqual([h["document_id"] for h in hits], ["setup-a"])
        self.assertEqual(search_documents(self.db, product_id="app-a",
                                          version="2.9", query="서버"), [])
        matched = match_event(self.db, product_id="app-a", version="2.10",
                              error_code="DB-1001", event_id="connection_failed")
        self.assertEqual(matched["rule_id"], "db-1001")
        self.assertEqual(match_event(self.db, product_id="app-a", version="2.9",
                                     error_code="DB-1001",
                                     event_id="connection_failed"), {"matched": False})
        a.write_text("# 데이터베이스\n\nDB-1001 방화벽 확인하세요.", encoding="utf-8")
        self.assertEqual(build(self.root, self.db)["updated"], 1)
        self.assertEqual(search_documents(self.db, product_id="app-a",
                                          version="2.10", query="포트를"), [])
        self.assertEqual(len(search_documents(self.db, product_id="app-a",
                                              version="2.10", query="방화벽")), 1)
        a.unlink()
        (self.root / "app-a/manuals/setup.md.meta.json").unlink()
        (self.root / "app-a/rules/db.json").unlink()
        self.assertEqual(build(self.root, self.db)["deleted"], 1)
        self.assertEqual(search_documents(self.db, product_id="app-a",
                                          version="2.10", query="방화벽"), [])
        self.assertEqual(match_event(self.db, product_id="app-a",
                                     error_code="DB-1001"), {"matched": False})

    def test_rebuild_and_incremental_search_match(self):
        self.write("app-a/manuals/a.md", "# First\n\nnetwork connection broken")
        self.write("app-a/manuals/b.md", "# Second\n\nrestart database")
        build(self.root, self.db)
        expected = search_documents(self.db, product_id="app-a", query="network")
        build(self.root, self.db, rebuild=True)
        self.assertEqual(expected, search_documents(self.db,
                                                     product_id="app-a", query="network"))
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('integrity-check')")


if __name__ == "__main__":
    unittest.main()
