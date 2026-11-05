"""T08 controlled CPU-only text RAG-answer comparison (not customer-PC benchmark).

Both models use the SAME llama.cpp binary/version, GGUF Q4_K_M, prompt template,
temperature, thread count, context and representative Korean manual excerpts.
This tests the *answer generation* layer, not different retrieval algorithms.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil


CASES = [
    {
        "id": "db-port",
        "manual": "데이터베이스 연결 오류가 발생하면 DB 서버 포트 3308을 확인한다. 웹 HTTPS 포트는 443이다.",
        "question": "데이터베이스 연결 오류가 발생하면 어떤 포트를 확인하나요?",
        "expected": ["3308"],
        "wrong": ["443"],
    },
    {
        "id": "local-api",
        "manual": "도움말 API는 127.0.0.1의 8765번 포트에서 제공한다. 관리자 웹 사이트는 8443번 포트를 사용한다.",
        "question": "PC 내부 도움말 API 포트 번호는?",
        "expected": ["8765"],
        "wrong": ["8443"],
    },
    {
        "id": "error-disambiguation",
        "manual": "E-104 오류는 시스템 시간을 동기화해야 한다. E-205 오류는 저장 공간 부족이므로 불필요한 파일을 정리한다.",
        "question": "오류 코드 E-205가 발생하면 무엇을 해야 하나요?",
        "expected": [],
        "acceptable_alternatives": ["저장", "파일", "정리"],
        "wrong": ["동기화"],
    },
    {
        "id": "keyboard-shortcut",
        "manual": "키보드 F7은 검색 메뉴, F8은 도움말 메뉴를 여는 단축키이다.",
        "question": "도움말을 열려면 어떤 단축키를 누르나요?",
        "expected": ["F8"],
        "wrong": ["F7"],
    },
    {
        "id": "manual-procedure",
        "manual": "업데이트하기 전에 반드시 프로그램을 종료한 다음 백업을 만든다. 데이터가 있는 상태에서 재설치는 금지한다.",
        "question": "업데이트 전에 반드시 먼저 해야 할 일은?",
        "expected": ["종료"],
        "wrong": ["재설치"],
    },
]
SYSTEM = "답변은 간단한 한국어 한 문장으로 하세요. 주어진 매뉴얼 내용만 사용하세요. 매뉴얼에 없는 정보는 추측하지 마세요."
THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(2**20), b""):
            h.update(chunk)
    return h.hexdigest()


def clean(text: str) -> str:
    text = THINK.sub("", ANSI.sub("", text))
    if "<think>" in text:
        text = text.split("<think>", 1)[0]
    return (text.replace("<|im_end|>", "").replace("<|eot_id|>", "")
            .replace("[end of text]", "").strip())


def invoke(binary: Path, model: Path, case: dict) -> dict:
    # Qwen3.5's strict built-in Jinja template rejects llama-completion's
    # single-turn -sys/-p synthetic conversation with "No user query found".
    # For a fair same-prompt comparison, feed both models explicit ChatML
    # system/user messages in raw completion mode instead.
    user_prompt = "매뉴얼: " + case["manual"] + "\n질문: " + case["question"] + " 답변:"
    prompt = (
        "<|im_start|>system\n" + SYSTEM + "<|im_end|>\n"
        + "<|im_start|>user\n" + user_prompt + "<|im_end|>\n"
        + "<|im_start|>assistant\n<think>\n\n</think>\n"
    )
    command = [
        str(binary), "-m", str(model),
        "-no-cnv", "-p", prompt,
        "-t", "4", "-c", "2048", "-n", "192", "-ngl", "0",
        "--temp", "0",
        "--simple-io", "--no-display-prompt", "--color", "off",
    ]
    begin = time.perf_counter()
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "HTTP_PROXY": "http://127.0.0.1:1",
             "HTTPS_PROXY": "http://127.0.0.1:1",
             "ALL_PROXY": "http://127.0.0.1:1"},
    )
    peak_rss = 0
    finished = threading.Event()

    def sample():
        nonlocal peak_rss
        while not finished.wait(0.05):
            try:
                peak_rss = max(peak_rss, psutil.Process(process.pid).memory_info().rss)
            except psutil.NoSuchProcess:
                break

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    try:
        stdout, stderr = process.communicate(input="", timeout=180)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
    finally:
        finished.set()
        sampler.join(timeout=2)
    seconds = round(time.perf_counter() - begin, 3)
    answer = clean(stdout)
    positive = all(token.casefold() in answer.casefold() for token in case["expected"])
    # For procedures, an accepted synonym/action can be enough even if the
    # reference describes both the problem (low storage) and the remedy (tidy files).
    alternatives = case.get("acceptable_alternatives", [])
    alternative_match = not alternatives or any(
        token.casefold() in answer.casefold() for token in alternatives
    )
    positive = positive and alternative_match
    negative = any(token.casefold() in answer.casefold() for token in case["wrong"])
    return {
        "case_id": case["id"],
        "expected": case["expected"],
        "acceptable_alternatives": case.get("acceptable_alternatives", []),
        "wrong": case["wrong"],
        "answer": answer,
        "exit_code": process.returncode,
        "latency_seconds": seconds,
        "peak_rss_mb": round(peak_rss / 2**20, 1),
        "expected_hit": bool(positive),
        "contradictory_text": bool(negative),
        "pass": process.returncode == 0 and positive and not negative,
        "stderr_tail": stderr[-400:] if process.returncode else "",
    }


def run_model(binary: Path, model: Path, expected_sha: str) -> dict:
    digest = sha256(model)
    if digest != expected_sha:
        raise ValueError(f"GGUF SHA256 mismatch for {model.name}: {digest}")
    results = [invoke(binary, model, case) for case in CASES]
    latencies = [x["latency_seconds"] for x in results]
    return {
        "model_file": model.name,
        "model_sha256": digest,
        "model_bytes": model.stat().st_size,
        "case_count": len(results),
        "passed": sum(x["pass"] for x in results),
        "expected_hit_count": sum(x["expected_hit"] for x in results),
        "contradictory_count": sum(x["contradictory_text"] for x in results),
        "latency_median_s": round(statistics.median(latencies), 3),
        "latency_mean_s": round(statistics.mean(latencies), 3),
        "peak_rss_max_mb": max(x["peak_rss_mb"] for x in results),
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llama-completion", type=Path, required=True)
    parser.add_argument("--qwen3", type=Path, required=True)
    parser.add_argument("--qwen35", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--llama-revision", required=True)
    args = parser.parse_args()
    if not args.llama_completion.is_file():
        parser.error("llama-completion binary is missing")
    results = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": "llama.cpp " + args.llama_revision,
        "host_os": platform.platform(),
        "cpu_logical": psutil.cpu_count(),
        "ram_total_mb": round(psutil.virtual_memory().total / 2**20),
        "fixed_inference": {"threads": 4, "ctx_size": 2048, "max_tokens": 192, "temp": 0, "gpu_layers": 0},
        "test_type": "Same-runtime generated answers from provided Korean excerpts, not end-to-end retrieval and not an 8GB Windows desktop",
        "models": {
            "Qwen3-1.7B-Q4_K_M": run_model(
                args.llama_completion, args.qwen3,
                "d2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5",
            ),
            "Qwen3.5-2B-Q4_K_M": run_model(
                args.llama_completion, args.qwen35,
                "9a3d0aa6c920f096441139b6a254542da855223fdad06855ea00c6c087fd713d",
            ),
        },
        "limitations": [
            "5 synthetic examples, not statistically reliable for production model selection.",
            "CPU runner is shared/virtualized; speed measurements are not user hardware predictions.",
            "No multimodal image testing; pure text GGUF.",
            "This experiment does not replace the production Qwen3/llama.cpp v0.8.0 package.",
        ],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "model_comparison.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print("T08_MODEL_COMPARISON=" + json.dumps({
        key: {k: v for k, v in item.items() if k in ("passed", "case_count", "latency_median_s", "peak_rss_max_mb")}
        for key, item in results["models"].items()
    }, ensure_ascii=True), flush=True)
    # A failed expected answer is recorded, not hidden or silently excluded.
    # Only a runtime failure means this CI comparison cannot be evaluated.
    if any(c["exit_code"] != 0 for data in results["models"].values() for c in data["cases"]):
        raise RuntimeError("At least one model invocation failed; inspect model_comparison.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
