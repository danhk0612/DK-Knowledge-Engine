"""T07 Python-side portable entrypoint and SQLite validation regression tests."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from distribution.server_entry import run, verify_database
from t07_prepare_db import produce


class PortableEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "knowledge" / "knowledge.db"
        produce(self.db)

    def test_real_builder_db_integrity_and_schema(self):
        result = verify_database(self.db)
        self.assertEqual(result["schema_version"], "1")
        self.assertEqual((result["documents"], result["rules"]), (1, 1))
        self.assertGreaterEqual(result["chunks"], 1)

    def test_corrupted_sqlite_rejected(self):
        invalid = self.root / "broken.db"
        invalid.write_bytes(b"this is not an SQLite database")
        with self.assertRaises(sqlite3.DatabaseError):
            verify_database(invalid)

    def test_unknown_schema_rejected(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE schema_info SET value='999' WHERE key='schema_version'")
        with self.assertRaisesRegex(ValueError, "schema version"):
            verify_database(self.db)

    def test_frozen_entrypoint_verify_only(self):
        self.assertEqual(run(["--verify-db", str(self.db)]), 0)
        self.assertEqual(run(["--verify-db", str(self.root / "missing.db")]), 1)

    def test_bad_settings_rejected_before_server(self):
        config = self.root / "config"
        config.mkdir()
        (config / "settings.json").write_text(
            json.dumps({"port": 8765, "allowed_origins": ["*"]}), encoding="utf-8"
        )
        self.assertEqual(run([], root=self.root), 1)

    def test_no_runtime_or_model_refuses_to_start(self):
        config = self.root / "config"
        config.mkdir()
        (config / "settings.json").write_text(
            json.dumps({"port": 8765, "allowed_origins": []}), encoding="utf-8"
        )
        self.assertEqual(run([], root=self.root), 1)


if __name__ == "__main__":
    unittest.main()
