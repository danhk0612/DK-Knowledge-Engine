"""T09 selection-contract regression tests: settings path, model/runtime and CLI flags."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from distribution.server_entry import portable_cli
from llm.local_llm import LlamaCli


class PortableSelectionTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        (self.root / "models").mkdir()
        (self.root / "runtime").mkdir()
        (self.root / "models" / "Qwen3-1.7B-Q4_K_M.gguf").write_bytes(b"gguf")
        (self.root / "models" / "other.gguf").write_bytes(b"other")
        (self.root / "runtime" / "llama-completion.exe").write_bytes(b"cli")
        (self.root / "runtime" / "other-completion.exe").write_bytes(b"other")
        self.default = {"port": 8765, "allowed_origins": []}

    @staticmethod
    def at(args: list[str], flag: str) -> str:
        return args[args.index(flag) + 1]

    def test_old_portable_settings_use_stable_defaults(self):
        cli = portable_cli(self.root, self.default)
        self.assertEqual(self.at(cli, "--threads"), "4")
        self.assertEqual(self.at(cli, "--ctx-size"), "4096")
        self.assertEqual(self.at(cli, "--max-tokens"), "192")
        self.assertEqual(self.at(cli, "--gpu-layers"), "0")
        self.assertEqual(self.at(cli, "--prompt-mode"), "qwen3")
        self.assertEqual(Path(self.at(cli, "--model")).name, "Qwen3-1.7B-Q4_K_M.gguf")

    def test_user_can_switch_model_runtime_and_resources(self):
        config = dict(self.default, model={
            "file": "models/other.gguf",
            "runtime": "runtime/other-completion.exe",
            "threads": 2, "context_size": 2048,
            "max_tokens": 96, "timeout_seconds": 260,
            "gpu_layers": 18, "prompt_mode": "raw_chatml",
        }, allowed_origins=["https://support.example"])
        cli = portable_cli(self.root, config)
        self.assertEqual(Path(self.at(cli, "--model")).name, "other.gguf")
        self.assertEqual(Path(self.at(cli, "--llama-cli")).name, "other-completion.exe")
        for flag, val in (("--threads", "2"), ("--ctx-size", "2048"),
                          ("--max-tokens", "96"), ("--timeout-seconds", "260"),
                          ("--gpu-layers", "18"), ("--prompt-mode", "raw_chatml")):
            self.assertEqual(self.at(cli, flag), val)
        self.assertIn("https://support.example", cli)

    def test_invalid_selection_rejected(self):
        bad = [
            {"file": "models/../secret.gguf"},
            {"file": "other.gguf"},
            {"file": "/tmp/model.gguf"},
            {"file": "models/missing.gguf"},
            {"file": "models/other.txt"},
            {"runtime": "runtime/missing.exe"},
            {"threads": 0}, {"threads": True},
            {"context_size": "4096"}, {"max_tokens": -1},
            {"timeout_seconds": 0}, {"gpu_layers": -1},
            {"prompt_mode": "unsupported"}, {"unsupported_key": "something"},
        ]
        for override in bad:
            with self.subTest(override=override), self.assertRaises((ValueError, FileNotFoundError)):
                portable_cli(self.root, dict(self.default, model=override))

    def test_symlink_cannot_escape_models_folder(self):
        outside = self.root / "outside.gguf"
        outside.write_bytes(b"model")
        target = self.root / "models" / "escape.gguf"
        try:
            target.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation unavailable")
        with self.assertRaises(ValueError):
            portable_cli(self.root, dict(self.default, model={"file": "models/escape.gguf"}))

    def test_other_settings_invalid(self):
        for settings in ({"port": 0, "allowed_origins": []},
                         {"port": True, "allowed_origins": []},
                         {"port": 8765, "allowed_origins": "https://example.com"},
                         {"port": 8765, "allowed_origins": [], "unknown": 1},
                         {"port": 8765, "allowed_origins": [], "model": "file"}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                portable_cli(self.root, settings)

    def test_old_qwen_mode_flags_remain_unchanged(self):
        with patch("llm.local_llm.subprocess.run", return_value=SimpleNamespace(
            returncode=0, stdout="3308", stderr=""
        )) as task:
            result = LlamaCli(self.root / "runtime/llama-completion.exe",
                              self.root / "models/other.gguf").generate("system", "question")
        self.assertEqual(result, "3308")
        argv = task.call_args.args[0]
        for arg in ("-sys", "--jinja", "--single-turn", "--reasoning"):
            self.assertIn(arg, argv)
        self.assertEqual(argv[argv.index("-ngl") + 1], "0")

    def test_raw_chatml_mode_uses_user_message_and_selected_gpu_layers(self):
        with patch("llm.local_llm.subprocess.run", return_value=SimpleNamespace(
            returncode=0, stdout="<think>ignore</think>3308", stderr=""
        )) as task:
            cli = LlamaCli(self.root / "runtime/llama-completion.exe",
                           self.root / "models/other.gguf", gpu_layers=12,
                           prompt_mode="raw_chatml")
            self.assertEqual(cli.generate("instructions", "find 3308"), "3308")
        args = task.call_args.args[0]
        self.assertEqual(args[args.index("-ngl") + 1], "12")
        self.assertIn("-no-cnv", args)
        self.assertNotIn("--jinja", args)
        prompt = args[args.index("-p") + 1]
        self.assertIn("<|im_start|>system\ninstructions", prompt)
        self.assertIn("<|im_start|>user\nfind 3308", prompt)


if __name__ == "__main__":
    unittest.main()
