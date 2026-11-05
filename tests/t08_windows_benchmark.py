"""T08 benchmark of the *distributed* T07 Windows ZIP on real CPU.

Measurements are for the hosted Windows runner only: do NOT present them as a
Windows 10/11 8-GB-customer-PC benchmark.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import psutil

from t07_package_smoke import call, pick_port, start_server, stop_server


def mb(value: int) -> float:
    return round(value / (1024 * 1024), 1)


class PeakSampler:
    """Approximate sum of RSS of portable API and its process descendants."""

    def __init__(self, root_pid: int):
        self.root_pid = root_pid
        self.samples: list[dict] = []
        self._end = threading.Event()
        self._thread = threading.Thread(target=self._watch, daemon=True)

    def _watch(self):
        while not self._end.is_set():
            try:
                root = psutil.Process(self.root_pid)
                children = root.children(recursive=True)
                processes = [root, *children]
                rss = 0
                for process in processes:
                    try:
                        rss += process.memory_info().rss
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                self.samples.append({"rss_mb": mb(rss), "process_count": len(processes)})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            self._end.wait(0.05)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_args):
        self._end.set()
        self._thread.join(timeout=5)

    def peak(self) -> float:
        return max((sample["rss_mb"] for sample in self.samples), default=0)


def measured_request(port: int, route: str, body: dict | None = None):
    start = time.perf_counter()
    answer = call(port, route, body)
    return answer, round(time.perf_counter() - start, 3)


def measure(package: Path) -> dict:
    port = pick_port()
    process = start_server(package, port)
    try:
        host = {
            "os": platform.platform(),
            "python_for_test_only": platform.python_version(),
            "cpu_logical": psutil.cpu_count(logical=True),
            "cpu_physical": psutil.cpu_count(logical=False),
            "ram_total_mb": mb(psutil.virtual_memory().total),
            "ram_available_at_start_mb": mb(psutil.virtual_memory().available),
            "packaged_model_bytes": (package / "models" / "Qwen3-1.7B-Q4_K_M.gguf").stat().st_size,
            "runner": os.environ.get("RUNNER_NAME", "local"),
            "8gb_target_machine": False,
            "gpu_acceleration": False,
        }
        with PeakSampler(process.pid) as sampler:
            health, health_time = measured_request(port, "/health")
            assert health["status"] == "ready" and health["llm_ready"]

            search, search_time = measured_request(port, "/search", {
                "product_id": "example-program", "version": "2.1.0", "query": "연결 오류",
            })
            assert search["results"] and "3308" in search["results"][0]["excerpt"]
            event, event_time = measured_request(port, "/event", {
                "product_id": "example-program", "version": "2.1.0",
                "event_id": "connection_failed", "error_code": "DB-1001",
            })
            assert event["matched"] and event["rule_id"] == "db-1001"

            # Cross-product and out-of-range-version isolation (no LLM needed).
            isolated, isolation_s = measured_request(port, "/search", {
                "product_id": "other-product", "version": "2.1.0", "query": "연결 오류",
            })
            assert isolated["results"] == []
            hidden, _ = measured_request(port, "/search", {
                "product_id": "example-program", "version": "9.0.0", "query": "연결 오류",
            })
            assert hidden["results"] == []
            absent, absent_s = measured_request(port, "/chat", {
                "product_id": "other-product", "version": "2.1.0",
                "question": "데이터베이스 연결 오류 포트",
            })
            assert absent["grounded"] is False and absent["sources"] == []

            queries = [
                "연결 오류가 나면 어떤 포트를 확인해야 하나요?",
                "데이터베이스 연결 오류 시 확인할 서버 포트 번호가 무엇인가요?",
                "연결 오류가 발생하면 포트 몇 번을 확인해야 하나요?",
            ]
            trials = []
            for question in queries:
                answer, seconds = measured_request(port, "/chat", {
                    "product_id": "example-program", "version": "2.1.0",
                    "question": question,
                })
                trials.append({
                    "question": question,
                    "latency_seconds": seconds,
                    "model_elapsed_seconds": answer.get("elapsed_seconds"),
                    "answer": answer["answer"],
                    "grounded": answer["grounded"],
                    "source_paths": [s["source_path"] for s in answer["sources"]],
                    "contains_expected_3308": "3308" in answer["answer"],
                })
            # Include one additional sample to observe a separate request's reload.
            latencies = [x["latency_seconds"] for x in trials]
        return {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "host": host,
            "http": {
                "health_seconds": health_time,
                "search_seconds": search_time,
                "event_seconds": event_time,
                "product_isolation_seconds": isolation_s,
                "no_evidence_seconds": absent_s,
                "product_isolation_pass": True,
                "version_isolation_pass": True,
                "no_evidence_pass": True,
            },
            "chat": {
                "trials": trials,
                "expected_3308_pass_count": sum(t["contains_expected_3308"] for t in trials),
                "trial_count": len(trials),
                "mean_seconds": round(statistics.mean(latencies), 3),
                "median_seconds": round(statistics.median(latencies), 3),
                "max_seconds": max(latencies),
            },
            "process_tree_peak_rss_mb": sampler.peak(),
            "peak_rss_measurement": "Sum of sampled process RSS (API + descendant llama CLI); shared pages may be double-counted; 50ms sampling",
            "limitations": [
                "Hosted Windows runner is not a controlled 8GB Windows 10/11 office PC.",
                "No physically disconnected network; packaged runtime PATH limited and proxy disabled.",
                "One artificial sample manual, not a general correctness benchmark.",
                "Each chat request launches a new model process (T04 contract).",
                "Browser enterprise HTTPS Local Network Access and SmartScreen not measured.",
            ],
        }
    finally:
        stop_server(process)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        with zipfile.ZipFile(args.zip) as archive:
            archive.extractall(folder)
        package = Path(folder) / "DK-Knowledge-Engine-Win-x64"
        result = measure(package)
    (args.output / "windows_cpu_baseline.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("T08_WINDOWS_BASELINE=" + json.dumps({
        "chat": {k: v for k, v in result["chat"].items() if k != "trials"},
        "peak_rss_mb": result["process_tree_peak_rss_mb"],
        "ram_total_mb": result["host"]["ram_total_mb"],
        "test": "hosted-windows-not-8gb-customer-machine",
    }, ensure_ascii=True), flush=True)
    # Failing an expected source-grounded answer is a measured regression, not
    # proof that a different model should be selected without a second benchmark.
    if result["chat"]["expected_3308_pass_count"] != result["chat"]["trial_count"]:
        raise AssertionError("At least one representative grounded Qwen3 answer missed 3308")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
