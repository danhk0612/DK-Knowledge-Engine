"""T09: test real independently rebuilt Windows ZIP with selected model/runtime.

The model file alias uses a hard link to the exact same validated GGUF bytes,
so this verifies switching *paths/options*, not compatibility with every GGUF.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from t07_package_smoke import call, offline_environment, pick_port, powershell


def start_with_current_settings(package: Path, port: int) -> subprocess.Popen:
    executable = package / "engine" / "DK-Knowledge-API.exe"
    process = subprocess.Popen(
        [str(executable)], cwd=package, env=offline_environment(),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(120):
        if process.poll() is not None:
            raise AssertionError(f"Configured portable server exited: {process.returncode}")
        try:
            response = call(port, "/health")
            if response["status"] == "ready" and response["llm_ready"]:
                return process
        except (OSError, AssertionError):
            pass
        time.sleep(.2)
    process.terminate()
    process.wait(timeout=15)
    raise AssertionError("Configured portable server never became ready")


def assert_answer(port: int) -> None:
    search = call(port, "/search", {
        "product_id": "example-program", "version": "2.1.0", "query": "연결 오류",
    })
    assert search["results"], search
    answer = call(port, "/chat", {
        "product_id": "example-program", "version": "2.1.0",
        "question": "데이터베이스 연결 오류 시 확인할 서버 포트는?",
    })
    assert answer["grounded"] and answer["sources"], answer
    assert "3308" in answer["answer"], answer
    print("T09_CHAT_ANSWER_OK " + json.dumps(answer["answer"], ensure_ascii=True), flush=True)


def restart_and_check(package: Path, port: int) -> None:
    server = start_with_current_settings(package, port)
    try:
        assert_answer(port)
    finally:
        server.terminate()
        server.wait(timeout=20)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("python tests/t09_config_smoke.py <new-t09-zip>")
    with tempfile.TemporaryDirectory() as folder:
        dest = Path(folder)
        with zipfile.ZipFile(sys.argv[1]) as archive:
            archive.extractall(dest)
        package = dest / "DK-Knowledge-Engine-Win-x64"
        settings_file = package / "config" / "settings.json"
        settings = json.loads(settings_file.read_text(encoding="utf-8"))
        assert settings["model"]["threads"] == 4
        assert settings["model"]["file"] == "models/Qwen3-1.7B-Q4_K_M.gguf"
        assert settings["model"]["prompt_mode"] == "raw_chatml"
        powershell(package / "Verify-AIHelp.ps1")
        port = pick_port()
        settings["port"] = port
        settings_file.write_text(json.dumps(settings), encoding="utf-8")
        restart_and_check(package, port)
        print("T09_DEFAULT_MODEL_OK", flush=True)

        # Additional named model and runtime are supplied by the user under
        # models/ and runtime/.  The test aliases validated identical bytes.
        main_model = package / "models" / "Qwen3-1.7B-Q4_K_M.gguf"
        alias_model = package / "models" / "selected-qwen3.gguf"
        os.link(main_model, alias_model)
        original_runtime = package / "runtime" / "llama-completion.exe"
        selected_runtime = package / "runtime" / "selected-completion.exe"
        shutil.copyfile(original_runtime, selected_runtime)
        settings["model"].update({
            "file": "models/selected-qwen3.gguf",
            "runtime": "runtime/selected-completion.exe",
            "threads": 2,
            "context_size": 2048,
            "max_tokens": 128,
            "timeout_seconds": 240,
            "gpu_layers": 0,
            "prompt_mode": "qwen3",
        })
        settings_file.write_text(json.dumps(settings), encoding="utf-8")
        powershell(package / "Verify-AIHelp.ps1")
        restart_and_check(package, port)
        print("T09_SELECTED_MODEL_AND_RUNTIME_OK", flush=True)

        # Qwen3's ChatML prompt handling is also supported by this CLI.
        settings["model"]["prompt_mode"] = "raw_chatml"
        settings_file.write_text(json.dumps(settings), encoding="utf-8")
        restart_and_check(package, port)
        print("T09_SELECTED_RAW_CHATML_OK", flush=True)

        # A non-existent model is rejected before it starts an HTTP listener.
        settings["model"]["file"] = "models/missing.gguf"
        settings_file.write_text(json.dumps(settings), encoding="utf-8")
        failure = subprocess.run(
            [str(package / "engine" / "DK-Knowledge-API.exe")],
            cwd=package, capture_output=True, text=True,
            errors="replace", env=offline_environment(), timeout=30,
        )
        assert failure.returncode != 0 and "does not exist" in failure.stderr, failure
        print("T09_MISSING_MODEL_REJECTED_OK", flush=True)


if __name__ == "__main__":
    main()
