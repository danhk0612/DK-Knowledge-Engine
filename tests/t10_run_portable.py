"""T10 executable ZIP quality gate on an author-side Windows test machine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from t07_package_smoke import pick_port, powershell, start_server, stop_server
from t10_eval import digest, evaluate, read_cases


REQUIRED_NOTICES = (
    "llama.cpp-LICENSE", "Qwen3-Apache-2.0-LICENSE",
    "CPython-LICENSE", "PyInstaller-COPYING.txt",
)


def run_package(package: Path, cases_file: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError("Refusing to replace an existing evidence file")
    db = package / "knowledge" / "knowledge.db"
    checked = powershell(package / "Verify-AIHelp.ps1")
    if "PACKAGE_VERIFY_OK" not in checked.stdout:
        raise AssertionError("Bundled package integrity verification did not succeed")
    notices = package / "licenses"
    if not all((notices / name).is_file() and (notices / name).stat().st_size > 0
               for name in REQUIRED_NOTICES):
        raise AssertionError("At least one bundled third-party license notice is missing")
    manifest = package / "manifest.json"
    if not manifest.is_file():
        raise AssertionError("Portable manifest is missing")

    cases = read_cases(cases_file)
    port = pick_port()
    server = start_server(package, port)  # Restricted PATH + unusable outbound proxies.
    try:
        report = evaluate(db, cases, port)
    finally:
        stop_server(server)
    report["verification_scope"] = {
        "package_manifest_sha256": digest(manifest),
        "bundled_files_integrity": "passed_by_existing_Verify-AIHelp.ps1",
        "third_party_license_notices": "present_not_legally_reviewed",
        "cpu_model": "uses_configured_portable_runtime",
        "restricted_path_and_invalid_proxy": True,
        "physically_disconnected_network": False,
        "browser_enterprise_lna_checked": False,
        "smartscreen_or_code_signing_checked": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_package(args.package, args.cases, args.output)
    print("T10_PORTABLE_QUALITY=" + json.dumps({
        "passed": report["passed_count"], "total": report["cases_count"],
        "failed_case_ids": [v["case_id"] for v in report["results"] if not v["passed"]],
    }, ensure_ascii=True), flush=True)
    return 0 if report["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
