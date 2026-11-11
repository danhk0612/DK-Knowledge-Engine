"""Regression: a Client ZIP may contain exactly one product's knowledge."""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import struct
import tempfile
import unittest

from builder.knowledge_builder import build
from builder.author_enrichment import SCHEMA as HINT_SCHEMA
from builder.embedding_index import SCHEMA as VECTOR_SCHEMA
from distribution.server_entry import (
    run, scope_product_database, verify_database, verify_product_database,
)


class ProductScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = self.root / "source"
        for product in ("alpha", "beta"):
            docs = source / product / "manuals"
            rules = source / product / "rules"
            docs.mkdir(parents=True)
            rules.mkdir(parents=True)
            (docs / "guide.md").write_text(
                f"# {product}\n\nUnique{product}Keyword setup instructions.\n", encoding="utf-8"
            )
            (docs / "guide.md.meta.json").write_text(
                json.dumps({"document_id": product + "-guide"}), encoding="utf-8"
            )
            (rules / "rule.json").write_text(json.dumps({
                "rule_id": product + "-rule",
                "product_id": product,
                "event_id": "setup_failed",
                "document_id": product + "-guide",
                "title": "Setup",
                "content": product + " setup assistance",
            }), encoding="utf-8")
        self.original = self.root / "author.db"
        build(source, self.original, rebuild=True)
        # Ensure optional search hints and vectors also respect deletion cascades.
        with closing(sqlite3.connect(self.original)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript(HINT_SCHEMA)
            db.executescript(VECTOR_SCHEMA)
            ids = db.execute("SELECT chunk_id FROM chunks").fetchall()
            with db:
                for (chunk_id,) in ids:
                    db.execute("INSERT INTO chunk_search_hints(chunk_id,hints) VALUES(?,?)",
                               (chunk_id, "search hint"))
                    db.execute(
                        "INSERT INTO chunk_embeddings(chunk_id,dimensions,vector) VALUES(?,?,?)",
                        (chunk_id, 16, struct.pack("<16f", *([0.1] * 16))),
                    )
                for key, value in {
                    "model_sha256": "a" * 64,
                    "profile": "generic",
                    "dimensions": "16",
                }.items():
                    db.execute("INSERT INTO embedding_metadata(key,value) VALUES(?,?)",
                               (key, value))
        self.before = hashlib.sha256(self.original.read_bytes()).hexdigest()
        package_dir = self.root / "package" / "knowledge"
        package_dir.mkdir(parents=True)
        self.copied = package_dir / "knowledge.db"
        shutil.copy2(self.original, self.copied)

    def test_product_scoping_deletes_every_other_product_without_touching_source(self):
        result = scope_product_database(self.copied, "alpha")
        self.assertEqual((result["documents"], result["rules"]), (1, 1))
        self.assertEqual(result["product_id"], "alpha")
        self.assertEqual(result["embedding"]["vectors"], result["chunks"])
        self.assertTrue(result["embedding"]["complete"])
        with closing(sqlite3.connect(self.copied)) as db:
            self.assertEqual(db.execute("SELECT DISTINCT product_id FROM documents").fetchall(),
                             [("alpha",)])
            self.assertEqual(db.execute("SELECT DISTINCT product_id FROM help_rules").fetchall(),
                             [("alpha",)])
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH 'uniquebetakeyword'"
            ).fetchone()[0], 0)
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM chunk_search_hints"
            ).fetchone()[0], result["chunks"])
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM chunk_embeddings"
            ).fetchone()[0], result["chunks"])
        self.assertEqual(hashlib.sha256(self.original.read_bytes()).hexdigest(), self.before)
        self.assertEqual(verify_database(self.original)["documents"], 2)

    def test_wrong_product_fails_without_modifying_copy(self):
        original_hash = hashlib.sha256(self.copied.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "no documents"):
            scope_product_database(self.copied, "missing")
        self.assertEqual(hashlib.sha256(self.copied.read_bytes()).hexdigest(), original_hash)

    def test_verifier_rejects_mixed_products_and_cross_product_request(self):
        with self.assertRaisesRegex(ValueError, "another product"):
            verify_product_database(self.copied, "alpha")
        self.assertEqual(run(["--verify-db", str(self.copied),
                              "--verify-product-id", "alpha"]), 1)
        self.assertEqual(run(["--scope-product-id", "alpha"],
                             root=self.root / "package"), 0)
        self.assertEqual(run(["--verify-db", str(self.copied),
                              "--verify-product-id", "alpha"]), 0)
        self.assertEqual(run(["--verify-db", str(self.copied),
                              "--verify-product-id", "beta"]), 1)


if __name__ == "__main__":
    unittest.main()
