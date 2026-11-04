"""T07 Windows portable-package smoke with actual Qwen GGUF and CPU llama.cpp.

Exercises an extracted ZIP without relying on a system Python interpreter.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import sqlite3
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from contextlib import closing
from pathlib import Path

from t07_prepare_db import produce


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def powershell(script: Path, *args: str, expect_success: bool = True) -> subprocess.CompletedProcess:
    exe = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    result = subprocess.run(
        [str(exe), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args],
        capture_output=True, text=True, errors="replace", timeout=150,
    )
    if expect_success and result.returncode != 0:
        raise AssertionError("PowerShell failed:\n" + result.stdout + "\n" + result.stderr)
    if not expect_success and result.returncode == 0:
        raise AssertionError("Expected rejected update or verification")
    return result


def call(port: int, endpoint: str, payload: dict | None = None) -> dict:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=240)
    try:
        raw = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if raw else {}
        conn.request("POST" if raw else "GET", endpoint, raw, headers)
        response = conn.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        if response.status != 200:
            raise AssertionError(f"{endpoint} HTTP {response.status}: {body}")
        return body
    finally:
        conn.close()


def pick_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return server.getsockname()[1]


def offline_environment() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = os.environ["SystemRoot"] + r"\System32;" + os.environ["SystemRoot"]
    env["HTTP_PROXY"] = "http://127.0.0.1:1"
    env["HTTPS_PROXY"] = "http://127.0.0.1:1"
    env["ALL_PROXY"] = "http://127.0.0.1:1"
    return env


def probe_cpu_runtime(package: Path) -> None:
    """Distinguish native DLL/CLI loading failures from Python HTTP errors."""
    executable = package / "runtime" / "llama-completion.exe"
    model = package / "models" / "Qwen3-1.7B-Q4_K_M.gguf"
    runtime_files = sorted(p.name for p in executable.parent.iterdir() if p.is_file())
    print("T07_RUNTIME_FILES:", runtime_files, flush=True)

    # CI-only PE import inspection: a Windows loader failure often reports
    # STATUS_DLL_NOT_FOUND without saying which import caused it.
    import pefile

    pe = pefile.PE(str(executable))
    dlls = sorted({entry.dll.decode("ascii", "replace")
                   for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])})
    print("T07_NATIVE_IMPORTS:", [
        {"dll": name,
         "in_runtime": (executable.parent / name).exists(),
         "in_system32": (Path(os.environ["SystemRoot"]) / "System32" / name).exists()}
        for name in dlls
    ], flush=True)
    pe.close()
    command = [
        str(executable),
        "-m", str(model),
        "-sys", "답변은 간단한 한국어 한 문장으로 하세요.",
        "-p", "매뉴얼: 연결 오류 시 포트 3308을 확인하세요.\\n질문: 확인할 포트는? 답변:",
        "-t", "4", "-c", "4096", "-n", "192", "-ngl", "0",
        "--temp", "0", "--reasoning", "off", "--jinja",
        "--single-turn", "--simple-io", "--no-display-prompt", "--color", "off",
    ]
    result = subprocess.run(
        command, input="", text=True, capture_output=True, encoding="utf-8",
        errors="replace", cwd=package, env=offline_environment(), timeout=180,
    )
    print(f"T07_DIRECT_CLI_EXIT={result.returncode}", flush=True)
    print("T07_DIRECT_CLI_STDERR:", ascii(result.stderr[-2500:]), flush=True)
    print("T07_DIRECT_CLI_STDOUT:", ascii(result.stdout[-1000:]), flush=True)
    if result.returncode != 0:
        normal = subprocess.run(
            command, input="", text=True, capture_output=True, encoding="utf-8",
            errors="replace", cwd=package, env=os.environ.copy(), timeout=180,
        )
        print(f"T07_NORMAL_PATH_CLI_EXIT={normal.returncode}", flush=True)
        print("T07_NORMAL_PATH_CLI_STDERR:", ascii(normal.stderr[-2500:]), flush=True)
        print("T07_NORMAL_PATH_CLI_STDOUT:", ascii(normal.stdout[-700:]), flush=True)
        raise AssertionError("Standalone packaged llama-completion failed before HTTP layer")
    if not result.stdout.strip():
        raise AssertionError("Standalone packaged llama-completion generated no output")


def start_server(package: Path, port: int) -> subprocess.Popen:
    settings = package / "config" / "settings.json"
    settings.write_text(
        json.dumps({"port": port, "allowed_origins": []}), encoding="utf-8"
    )
    exe = package / "engine" / "DK-Knowledge-API.exe"
    # The target executable is self-contained; no system Python or network setup.
    env = offline_environment()
    process = subprocess.Popen(
        [str(exe)], cwd=package, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    limit = time.time() + 35
    while time.time() < limit:
        if process.poll() is not None:
            raise AssertionError("Bundled engine exited before becoming ready")
        try:
            health = call(port, "/health")
            if health["status"] == "ready" and health["llm_ready"]:
                return process
        except (OSError, ValueError, AssertionError):
            pass
        time.sleep(0.25)
    process.terminate()
    process.wait(timeout=10)
    raise AssertionError("Packaged API startup timed out")


def stop_server(process: subprocess.Popen) -> None:
    process.terminate()
    process.wait(timeout=15)


def verify_content(package: Path, port: int, expected_port: int, *, test_chat: bool) -> None:
    result = call(port, "/search", {
        "product_id": "example-program", "version": "2.1.0", "query": "연결 오류",
    })
    assert result["results"], result
    assert str(expected_port) in result["results"][0]["excerpt"], result
    error = call(port, "/event", {
        "product_id": "example-program", "version": "2.1.0",
        "event_id": "connection_failed", "error_code": "DB-1001",
    })
    assert error["matched"] and str(expected_port) in error["content"], error
    if test_chat:
        answer = call(port, "/chat", {
            "product_id": "example-program", "version": "2.1.0",
            "question": "연결 오류가 나면 어떤 포트를 확인해야 하나요?",
        })
        assert answer["grounded"] and str(expected_port) in answer["answer"], answer
        assert answer["sources"][0]["source_path"] == "example-program/manuals/setup.md", answer
        print("T07_REAL_CPU_CHAT:", json.dumps(answer["answer"], ensure_ascii=True), flush=True)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tests/t07_package_smoke.py <package.zip>")
    archive = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory() as folder:
        temp = Path(folder)
        with zipfile.ZipFile(archive) as zipfile_obj:
            zipfile_obj.extractall(temp / "extracted")
        package = temp / "extracted" / "DK-Knowledge-Engine-Win-x64"
        assert (package / "engine" / "DK-Knowledge-API.exe").is_file()
        assert (package / "runtime" / "llama-completion.exe").is_file()
        assert (package / "models" / "Qwen3-1.7B-Q4_K_M.gguf").is_file()
        assert (package / "knowledge" / "knowledge.db").is_file()
        assert (package / "licenses" / "llama.cpp-LICENSE").is_file()
        assert (package / "licenses" / "Qwen3-Apache-2.0-LICENSE").is_file()

        verify = package / "Verify-AIHelp.ps1"
        update = package / "Update-Knowledge.ps1"
        checked = powershell(verify)
        assert "PACKAGE_VERIFY_OK" in checked.stdout, checked.stdout
        print("T07_PACKAGE_VERIFY_OK", flush=True)
        probe_cpu_runtime(package)

        api_port = pick_port()
        process = start_server(package, api_port)
        try:
            verify_content(package, api_port, 3308, test_chat=True)
        finally:
            stop_server(process)

        current = package / "knowledge" / "knowledge.db"
        before_hash = sha256(current)
        replacement = temp / "new-knowledge.db"
        produce(replacement, port=3322)
        bad_hash = "0" * 64
        powershell(update, "-SourceDb", str(replacement), "-ExpectedSha256", bad_hash,
                   expect_success=False)
        assert sha256(current) == before_hash, "Invalid hash changed current DB"

        valid_hash = sha256(replacement)
        updated = powershell(update, "-SourceDb", str(replacement),
                            "-ExpectedSha256", valid_hash)
        assert "KNOWLEDGE_UPDATE_OK" in updated.stdout, updated.stdout
        assert sha256(current) == valid_hash
        powershell(verify)
        process = start_server(package, api_port)
        try:
            verify_content(package, api_port, 3322, test_chat=False)
            with closing(sqlite3.connect(current)) as db:
                stale = db.execute("SELECT count(*) FROM chunks WHERE content LIKE '%3308%'").fetchone()[0]
                assert stale == 0, "Old knowledge remained after replacement"
        finally:
            stop_server(process)

        rolled_back = powershell(update, "-Rollback")
        assert "KNOWLEDGE_UPDATE_OK" in rolled_back.stdout, rolled_back.stdout
        assert sha256(current) == before_hash
        powershell(verify)
        process = start_server(package, api_port)
        try:
            verify_content(package, api_port, 3308, test_chat=False)
        finally:
            stop_server(process)

        # Verification must detect binary/script tampering, not just DB damage.
        launcher = package / "Start-AIHelp.cmd"
        original = launcher.read_bytes()
        launcher.write_bytes(original + b"rem unexpected edit\n")
        powershell(verify, expect_success=False)
        launcher.write_bytes(original)
        powershell(verify)
        print("T07_OFFLINE_PORTABLE_UPDATE_ROLLBACK_SMOKE_OK", flush=True)


if __name__ == "__main__":
    main()
