"""T10 local-only RAG quality + HTTP boundary evaluator.

Runs against an ALREADY RUNNING loopback engine. It neither builds the engine
nor sends user documents to a remote service. Report omits question/answer
bodies and source paths by default. This is a deterministic gate, not a claim
that keyword matching proves semantic correctness.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from search.knowledge_search import search_documents


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def read_cases(path: Path) -> list[dict]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, list) or not value:
        raise ValueError("Cases must be a non-empty JSON array")
    seen: set[str] = set()
    allowed = {
        "id", "kind", "product_id", "version", "query", "question",
        "event_id", "error_code", "screen_id", "expect_results",
        "expect_matched", "expected_rule_id", "expected_grounded",
        "expected_source", "forbidden_sources", "expected_any",
        "forbidden_any", "evidence_any",
    }
    for case in value:
        if not isinstance(case, dict) or set(case) - allowed:
            raise ValueError("Case must be an object with known keys")
        cid, kind, product = case.get("id"), case.get("kind"), case.get("product_id")
        if not isinstance(cid, str) or not cid or cid in seen:
            raise ValueError("Case IDs must be unique, non-empty strings")
        seen.add(cid)
        if kind not in ("search", "chat", "event"):
            raise ValueError("Case kind must be search, chat or event")
        if not isinstance(product, str) or not product.strip():
            raise ValueError("Every case requires a product_id")
        for name in ("expected_source", "expected_rule_id", "query",
                     "question", "event_id", "error_code", "screen_id", "version"):
            if case.get(name) is not None and not isinstance(case[name], str):
                raise ValueError(f"{name} must be a string")
        if kind == "search" and (not case.get("query") or type(case.get("expect_results")) is not bool):
            raise ValueError("Search requires query and boolean expect_results")
        if kind == "chat" and (not case.get("question") or type(case.get("expected_grounded")) is not bool):
            raise ValueError("Chat requires question and boolean expected_grounded")
        if kind == "event" and (
            not (case.get("event_id") or case.get("error_code"))
            or type(case.get("expect_matched")) is not bool
        ):
            raise ValueError("Event requires an event/error code and boolean expect_matched")
        # A whitespace-only term can match nearly any natural-language answer
        # and turn a quality gate into a false pass.
        for key in ("forbidden_sources", "expected_any", "forbidden_any", "evidence_any"):
            if key in case and (not isinstance(case[key], list) or not all(
                isinstance(x, str) and x.strip() for x in case[key]
            )):
                raise ValueError(f"{key} must contain non-blank strings")
        for key in ("expected_source", "expected_rule_id"):
            if case.get(key) is not None and not case[key].strip():
                raise ValueError(f"{key} must not be blank")
        if kind == "chat" and case["expected_grounded"] and not case.get("expected_any"):
            raise ValueError("Expected grounded answers require expected_any")
    return value


def request(port: int, route: str, body: dict | None = None,
            *, method: str | None = None, headers: dict | None = None
            ) -> tuple[int, dict, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=240)
    try:
        payload = (json.dumps(body, ensure_ascii=False).encode("utf-8")
                   if body is not None else None)
        outgoing = {"Content-Type": "application/json"} if payload is not None else {}
        outgoing.update(headers or {})
        conn.request(method or ("POST" if payload is not None else "GET"),
                     route, body=payload, headers=outgoing)
        response = conn.getresponse()
        raw = response.read()
        data = json.loads(raw.decode("utf-8")) if raw else {}
        return response.status, data, dict(response.getheaders())
    finally:
        conn.close()


def check_terms(text: str, case: dict, failures: list[str]) -> None:
    acceptable = case.get("expected_any", [])
    denied = case.get("forbidden_any", [])
    if acceptable and not any(word.casefold() in text.casefold() for word in acceptable):
        failures.append("expected-text-not-present")
    if denied and any(word.casefold() in text.casefold() for word in denied):
        failures.append("forbidden-text-present")


def source_belongs_to_product(db: Path, source_path: str, product_id: str) -> bool:
    """Check real DB ownership; T14 accepts root-level documents without a product folder."""
    with sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True) as connection:
        return connection.execute(
            "SELECT 1 FROM documents WHERE source_path = ? AND product_id = ? LIMIT 1",
            (source_path, product_id),
        ).fetchone() is not None


def evaluate_case(db: Path, port: int, case: dict) -> dict:
    failures: list[str] = []
    kind = case["kind"]
    body: dict[str, Any] = {"product_id": case["product_id"]}
    if "version" in case:
        body["version"] = case["version"]
    if kind == "search":
        body["query"] = case["query"]
    elif kind == "chat":
        body["question"] = case["question"]
    else:
        for field in ("event_id", "error_code", "screen_id"):
            if field in case:
                body[field] = case[field]
    try:
        status, response, _ = request(port, "/" + kind, body)
    except (OSError, TimeoutError, ValueError):
        return {"case_id": case["id"], "kind": kind, "passed": False,
                "failures": ["request-failed"]}
    if status != 200:
        return {"case_id": case["id"], "kind": kind, "passed": False,
                "failures": [f"unexpected-http-status-{status}"]}

    expected_source = case.get("expected_source")
    blocked = set(case.get("forbidden_sources", []))
    if kind == "search":
        hits = response.get("results")
        if not isinstance(hits, list):
            failures.append("invalid-search-response")
            hits = []
        if bool(hits) != case["expect_results"]:
            failures.append("unexpected-search-hit-presence")
        sources = {h.get("source_path") for h in hits if isinstance(h, dict)}
        if expected_source and expected_source not in sources:
            failures.append("expected-source-missing")
        if blocked.intersection(sources):
            failures.append("cross-product-or-version-source")
        if any(not isinstance(p, str) or
               not source_belongs_to_product(db, p, case["product_id"])
               for p in sources):
            failures.append("wrong-product-source")

    elif kind == "event":
        if response.get("matched") is not case["expect_matched"]:
            failures.append("incorrect-event-match")
        if case["expect_matched"]:
            if case.get("expected_rule_id") and response.get("rule_id") != case["expected_rule_id"]:
                failures.append("wrong-approved-rule")
            source = response.get("source") or {}
            if expected_source and source.get("source_path") != expected_source:
                failures.append("wrong-event-provenance")
            if not isinstance(source, dict) or not source_belongs_to_product(
                db, str(source.get("source_path", "")), case["product_id"]
            ):
                failures.append("wrong-product-source")
            check_terms(str(response.get("content", "")), case, failures)

    else:
        expected_grounded = case["expected_grounded"]
        if response.get("grounded") is not expected_grounded:
            failures.append("grounding-flag-mismatch")
        sources = response.get("sources")
        if not isinstance(sources, list):
            failures.append("invalid-chat-sources")
            sources = []
        if not expected_grounded:
            if sources:
                failures.append("ungrounded-response-has-sources")
        else:
            if not sources:
                failures.append("grounded-response-has-no-sources")
            search_hits = search_documents(
                db, product_id=case["product_id"],
                query=case["question"], version=case.get("version"), limit=5,
            )
            valid_hits = {
                (hit["document_id"], hit["chunk_id"], hit["source_path"], hit["page_from"]): hit
                for hit in search_hits
            }
            matched_evidence: list[str] = []
            returned_paths: set[str] = set()
            for source in sources:
                if not isinstance(source, dict):
                    failures.append("malformed-citation")
                    continue
                key = (source.get("document_id"), source.get("chunk_id"),
                       source.get("source_path"), source.get("page_from"))
                evidence = valid_hits.get(key)
                if evidence is None:
                    failures.append("citation-not-in-requested-retrieval")
                else:
                    matched_evidence.append(evidence["excerpt"])
                returned_paths.add(source.get("source_path"))
            if expected_source and expected_source not in returned_paths:
                failures.append("expected-source-missing")
            if blocked.intersection(returned_paths):
                failures.append("cross-product-or-version-source")
            required_evidence = case.get("evidence_any", [])
            if required_evidence and not any(
                term.casefold() in excerpt.casefold()
                for term in required_evidence for excerpt in matched_evidence
            ):
                failures.append("answer-evidence-not-present")
            check_terms(str(response.get("answer", "")), case, failures)

    return {"case_id": case["id"], "kind": kind,
            "passed": not failures, "failures": sorted(set(failures))}


def security_checks(port: int) -> list[dict]:
    """HTTP boundary checks; NOT physical air-gap or browser policy validation."""
    probes = [
        ("reject-untrusted-origin", "POST", "/search",
         {"product_id": "product-alpha", "query": "연결 오류"},
         {"Origin": "https://untrusted.example.invalid"}, 403),
        ("reject-spoofed-host", "GET", "/health", None,
         {"Host": "attacker.example.invalid"}, 403),
        ("allow-valid-loopback-host", "GET", "/health", None, {}, 200),
        ("reject-untrusted-preflight", "OPTIONS", "/chat", None,
         {"Origin": "https://untrusted.example.invalid",
          "Access-Control-Request-Method": "POST"}, 403),
    ]
    results = []
    for cid, method, route, body, headers, expected in probes:
        failures: list[str] = []
        try:
            status, _, response_headers = request(
                port, route, body, method=method, headers=headers,
            )
            if status != expected:
                failures.append(f"unexpected-http-status-{status}")
            if expected == 403 and "Access-Control-Allow-Origin" in response_headers:
                failures.append("denied-origin-received-allow-header")
        except (OSError, TimeoutError, ValueError):
            failures.append("request-failed")
        results.append({"case_id": cid, "kind": "http-security",
                        "passed": not failures, "failures": failures})
    return results


def evaluate(db: Path, cases: list[dict], port: int) -> dict:
    results = [evaluate_case(db, port, case) for case in cases]
    results += security_checks(port)
    by_kind = Counter()
    for result in results:
        by_kind[result["kind"]] += 1
    return {
        "schema_version": 1,
        "collected_utc": datetime.now(timezone.utc).isoformat(),
        "knowledge_sha256": digest(db),
        "cases_count": len(results),
        "passed_count": sum(item["passed"] for item in results),
        "failed_count": sum(not item["passed"] for item in results),
        "cases_by_kind": dict(sorted(by_kind.items())),
        "results": results,
        "limitations": [
            "Literal expected/forbidden terms are only a proxy for semantic correctness.",
            "Citation matching confirms retrieval provenance, not that the answer is entailed by the citation.",
            "HTTP Host and Origin checks do not prove physical air-gap, browser enterprise policy, or code signing.",
            "Real customer manual answers still require authorized human review of question, answer and evidence.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error("Knowledge database does not exist")
    if not 1 <= args.port <= 65535:
        parser.error("Port must be 1..65535")
    cases = read_cases(args.cases)
    if args.output.exists():
        parser.error("Output file already exists; will not overwrite previous evidence")
    result = evaluate(args.database, cases, args.port)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print("T10_QUALITY_CHECK " + json.dumps({
        "passed": result["passed_count"],
        "total": result["cases_count"],
        "failed": [v["case_id"] for v in result["results"] if not v["passed"]],
    }, ensure_ascii=True), flush=True)
    return 0 if result["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
