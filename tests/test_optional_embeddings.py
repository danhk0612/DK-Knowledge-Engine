"""T19 CPU-only semantic indexing and hybrid retrieval without model downloads."""
from __future__ import annotations

import hashlib
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from builder.knowledge_builder import build
from distribution.server_entry import portable_cli, verify_database, compact_without_embeddings, run
from embedding.llama_embedder import LlamaEmbedder
from search.knowledge_search import search_documents


class FakeEncoder:
    def __init__(self):
        self.inputs = []

    def encode(self, text):
        self.inputs.append(text)
        # Deliberately semantic test signal: the query wording does not occur in
        # the original chunks. No external inference or subjective model claims.
        selected = any(token in text for token in ("전원", "동작 중지", "장치 종료"))
        return ([1.0] + [0.0] * 15) if selected else ([0.0, 1.0] + [0.0] * 14)


class HybridTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.docs = self.root / "sources"
        (self.docs / "device" / "manuals").mkdir(parents=True)
        (self.docs / "other" / "manuals").mkdir(parents=True)
        (self.docs / "device" / "manuals" / "stop.md").write_text(
            "안전을 위해 전원 스위치를 5초간 누릅니다.", encoding="utf-8")
        (self.docs / "other" / "manuals" / "stop.md").write_text(
            "전원 스위치를 절대 누르지 마세요.", encoding="utf-8")
        (self.docs / "device" / "manuals" / "clock.md").write_text(
            "시스템 날짜와 시간을 확인합니다.", encoding="utf-8")
        self.db = self.root / "knowledge.db"
        self.executable = self.root / "llama-embedding.exe"
        self.model = self.root / "small.gguf"
        self.executable.write_bytes(b"binary")
        self.model.write_bytes(b"gguf")
        self.fake = FakeEncoder()

    def build_embeddings(self, profile="generic"):
        with patch("builder.embedding_index.LlamaEmbedder", return_value=self.fake):
            return build(self.docs, self.db, rebuild=True,
                         embedding_runtime=self.executable,
                         embedding_model=self.model,
                         embedding_profile=profile)

    def test_vector_index_rescues_semantic_query_without_client_llm_change(self):
        build(self.docs, self.db, rebuild=True)
        query = "장치 종료를 안전하게 진행하려면?"
        self.assertEqual(search_documents(self.db, product_id="device", query=query), [])
        result = self.build_embeddings()
        self.assertEqual(result["embedding_index"]["indexed"], 3)
        self.assertTrue(result["embedding_index"]["complete"])
        self.assertTrue(verify_database(self.db)["embedding"]["complete"])
        hit = search_documents(self.db, product_id="device", query=query,
                               embedder=self.fake, min_similarity=0.8)
        self.assertEqual([h["source_path"] for h in hit], ["device/manuals/stop.md"])
        self.assertIn("5초", hit[0]["excerpt"])
        self.assertEqual(search_documents(self.db, product_id="other", query=query,
                                          embedder=self.fake)[0]["source_path"],
                         "other/manuals/stop.md")

    def test_encoder_prefix_and_metadata_are_consistent(self):
        self.build_embeddings(profile="e5")
        self.assertTrue(all(x.startswith("passage: ") for x in self.fake.inputs))
        self.fake.inputs.clear()
        search_documents(self.db, product_id="device",
                         query="장치 종료를 안전하게 진행하려면?", embedder=self.fake)
        self.assertTrue(self.fake.inputs[0].startswith("query: "))
        with closing(sqlite3.connect(self.db)) as db:
            meta = dict(db.execute("SELECT key,value FROM embedding_metadata"))
            self.assertEqual(meta["profile"], "e5")
            self.assertEqual(meta["model_sha256"], hashlib.sha256(b"gguf").hexdigest())

    def test_legacy_db_and_partial_index_fall_back_to_fts(self):
        build(self.docs, self.db, rebuild=True)
        self.assertEqual(len(search_documents(self.db, product_id="device",
                                              query="전원", embedder=self.fake)), 1)
        self.assertEqual(self.fake.inputs, [])  # FTS exact hit avoids cold-loading GGUF
        with patch("builder.embedding_index.LlamaEmbedder", return_value=self.fake):
            result = build(self.docs, self.db, rebuild=True,
                           embedding_runtime=self.executable, embedding_model=self.model,
                           embedding_max_chunks=1)
        self.assertFalse(result["embedding_index"]["complete"])
        self.assertFalse(verify_database(self.db)["embedding"]["complete"])

    def test_default_client_db_compaction_keeps_original_knowledge(self):
        self.build_embeddings(profile="e5")
        author_bytes = self.db.read_bytes()
        packaged_root = self.root / "client"
        (packaged_root / "knowledge").mkdir(parents=True)
        packaged_db = packaged_root / "knowledge" / "knowledge.db"
        shutil.copyfile(self.db, packaged_db)
        self.assertEqual(run(["--compact-no-embeddings"], root=packaged_root), 0)
        self.assertEqual(self.db.read_bytes(), author_bytes)
        self.assertNotIn("embedding", verify_database(packaged_db))
        self.assertIn("embedding", verify_database(self.db))
        self.assertLess(packaged_db.stat().st_size, self.db.stat().st_size)
        results = search_documents(packaged_db, product_id="device", query="전원")
        self.assertEqual(len(results), 1)
        report = compact_without_embeddings(packaged_db)
        self.assertEqual(report["removed_vectors"], 0)

    def test_portable_settings_embed_selection_is_strictly_local(self):
        (self.root / "runtime").mkdir()
        (self.root / "models").mkdir()
        (self.root / "runtime" / "llama-completion.exe").write_bytes(b"llm")
        (self.root / "models" / "Qwen3-1.7B-Q4_K_M.gguf").write_bytes(b"default")
        (self.root / "runtime" / "llama-embedding.exe").write_bytes(b"embed")
        (self.root / "models" / "small.gguf").write_bytes(b"small")
        config = {
            "port": 8765, "allowed_origins": [],
            "embedding": {
                "file": "models/small.gguf",
                "runtime": "runtime/llama-embedding.exe",
                "min_similarity": 0.72,
            },
        }
        flags = portable_cli(self.root, config)
        self.assertEqual(flags[flags.index("--embedding-model") + 1],
                         str((self.root / "models" / "small.gguf").resolve()))
        config["embedding"]["file"] = "../secret.gguf"
        with self.assertRaises(ValueError):
            portable_cli(self.root, config)


class EmbedderAdapterTests(unittest.TestCase):
    def test_array_output_normalization_and_invalid_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            exe = Path(temporary) / "llama-embedding.exe"
            model = Path(temporary) / "model.gguf"
            exe.write_bytes(b"exe")
            model.write_bytes(b"gguf")
            embedder = LlamaEmbedder(exe, model)
            raw = "[[" + ",".join(["3.0", "4.0"] + ["0"] * 14) + "]]"
            with patch("embedding.llama_embedder.subprocess.run",
                       return_value=SimpleNamespace(returncode=0, stdout=raw, stderr="")) as call:
                v = embedder.encode("example text\\nsecond paragraph")
                command = call.call_args.args[0]
            self.assertIn("--embd-separator", command)
            self.assertNotEqual(command[command.index("--embd-separator") + 1], "\\n")
            self.assertAlmostEqual(v[0], 0.6)
            self.assertAlmostEqual(v[1], 0.8)
            self.assertIn("--embd-output-format", call.call_args.args[0])
            with patch("embedding.llama_embedder.subprocess.run",
                       return_value=SimpleNamespace(returncode=0, stdout="[[0,1]]", stderr="")):
                with self.assertRaisesRegex(RuntimeError, "embedding output"):
                    embedder.encode("example")


if __name__ == "__main__":
    unittest.main()
