"""T05 real loopback HTTP regression tests, including T02/T03/T04 integration."""

from __future__ import annotations

import http.client
import json
import threading
import unittest
import tempfile
from pathlib import Path

from api.localhost_api import KnowledgeHttpServer
from builder.knowledge_builder import build


class FakeGenerator:
    def __init__(self):
        self.calls = []

    def generate(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return "DB 서버 포트 3308을 확인하십시오."


class BlockingGenerator(FakeGenerator):
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def generate(self, system: str, user: str) -> str:
        self.entered.set()
        if not self.release.wait(5):
            raise RuntimeError("Timed out waiting for test thread")
        return super().generate(system, user)


class LocalApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name) / "sources"
        db = Path(self.temp.name) / "knowledge.db"
        manuals_a = root / "app-a" / "manuals"
        manuals_a.mkdir(parents=True)
        manuals_b = root / "app-b" / "manuals"
        manuals_b.mkdir(parents=True)

        a = manuals_a / "setup.md"
        a.write_text("# DB 오류\n\n연결 오류 발생 시 서버 포트 3308을 확인하십시오.", encoding="utf-8")
        a.with_name(a.name + ".meta.json").write_text(
            '{"document_id":"guide-a","version_from":"2.0","version_to":"3.0"}',
            encoding="utf-8",
        )
        (manuals_b / "guide.txt").write_text("연결 오류 발생 시 서버 포트 9999를 확인하십시오.", encoding="utf-8")
        rules = root / "app-a" / "rules"
        rules.mkdir()
        (rules / "db.json").write_text(
            json.dumps({
                "rule_id": "db-1001", "product_id": "app-a", "event_id": "connection_failed",
                "error_code": "DB-1001", "screen_id": "db_settings", "document_id": "guide-a",
                "title": "연결 실패", "content": "연결 포트 3308을 확인하십시오.",
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        build(root, db)
        self.generator = FakeGenerator()
        self.server = KnowledgeHttpServer(
            db, port=0, generator=self.generator,
            allowed_origins=("https://trusted.example",),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_server)

    def _stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, method, path, data=None, headers=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=6)
        try:
            outgoing = dict(headers or {})
            if raw is None and data is not None:
                raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
                outgoing.setdefault("Content-Type", "application/json")
            conn.request(method, path, body=raw, headers=outgoing)
            result = conn.getresponse()
            body = result.read()
            try:
                decoded = json.loads(body.decode("utf-8")) if body else None
            except json.JSONDecodeError:
                decoded = body
            return result.status, decoded, {k.lower(): v for k, v in result.getheaders()}
        finally:
            conn.close()

    def test_server_binds_only_ipv4_loopback(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        self.assertGreater(self.server.server_port, 0)

    def test_health_exposes_ready_state_without_model_paths(self):
        status, result, _ = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["knowledge_version"], "1")
        self.assertTrue(result["llm_ready"])
        self.assertNotIn(str(self.server.database), json.dumps(result))

    def test_search_product_isolation_version_and_sources(self):
        status, result, _ = self.request("POST", "/search", {
            "product_id": "app-a", "version": "2.5", "query": "연결",
        })
        self.assertEqual(status, 200)
        self.assertEqual([x["document_id"] for x in result["results"]], ["guide-a"])
        self.assertEqual(result["results"][0]["source_path"], "app-a/manuals/setup.md")
        self.assertEqual(self.request("POST", "/search", {
            "product_id": "app-a", "version": "1.9", "query": "연결",
        })[1]["results"], [])
        self.assertNotIn("9999", json.dumps(result))

    def test_event_matches_approved_rule_without_model(self):
        req = {"product_id": "app-a", "version": "2.5", "error_code": "DB-1001",
               "event_id": "connection_failed", "screen_id": "db_settings"}
        status, result, _ = self.request("POST", "/event", req)
        self.assertEqual(status, 200)
        self.assertTrue(result["matched"])
        self.assertEqual(result["rule_id"], "db-1001")
        self.assertEqual(result["source"]["document_id"], "guide-a")
        self.assertEqual(self.generator.calls, [])
        req["version"] = "1.0"
        self.assertEqual(self.request("POST", "/event", req)[1], {"matched": False})
        req["version"] = "2.5"
        req["product_id"] = "app-b"
        self.assertEqual(self.request("POST", "/event", req)[1], {"matched": False})

    def test_chat_uses_retrieved_evidence_and_citations(self):
        status, result, _ = self.request("POST", "/chat", {
            "product_id": "app-a", "version": "2.5", "question": "연결 오류 포트",
        })
        self.assertEqual(status, 200)
        self.assertTrue(result["grounded"])
        self.assertIn("3308", result["answer"])
        self.assertEqual(result["sources"][0]["document_id"], "guide-a")
        self.assertIn("3308", self.generator.calls[0][1])
        self.assertNotIn("9999", self.generator.calls[0][1])

    def test_chat_no_retrieval_does_not_call_model(self):
        status, result, _ = self.request("POST", "/chat", {
            "product_id": "app-a", "version": "2.5", "question": "블루투스안테나",
        })
        self.assertEqual(status, 200)
        self.assertFalse(result["grounded"])
        self.assertEqual(result["sources"], [])
        self.assertEqual(self.generator.calls, [])

    def test_chat_without_configured_model_returns_503(self):
        self.server.generator = None
        status, result, _ = self.request("POST", "/chat", {
            "product_id": "app-a", "version": "2.5", "question": "연결 오류",
        })
        self.assertEqual((status, result["error"]), (503, "llm_unavailable"))
        self.assertEqual(self.request("GET", "/health")[1]["llm_ready"], False)
        self.assertEqual(self.request("POST", "/search", {
            "product_id": "app-a", "version": "2.5", "query": "연결",
        })[0], 200)

    def test_only_one_model_request_runs_at_once(self):
        blocked = BlockingGenerator()
        self.server.generator = blocked
        first = {}

        def invoke():
            first["result"] = self.request("POST", "/chat", {
                "product_id": "app-a", "version": "2.5", "question": "연결 오류",
            })

        thread = threading.Thread(target=invoke)
        thread.start()
        try:
            self.assertTrue(blocked.entered.wait(3))
            status, result, _ = self.request("POST", "/chat", {
                "product_id": "app-a", "version": "2.5", "question": "연결 오류",
            })
            self.assertEqual((status, result["error"]), (429, "llm_busy"))
        finally:
            blocked.release.set()
            thread.join(timeout=6)
        self.assertEqual(first["result"][0], 200)
        self.assertEqual(len(blocked.calls), 1)

    def test_explicit_origin_preflight_and_private_network_allow(self):
        origin = "https://trusted.example"
        status, result, hdrs = self.request("OPTIONS", "/chat", headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
            "Access-Control-Request-Private-Network": "true",
        })
        self.assertEqual(status, 204)
        self.assertEqual(result, None)
        self.assertEqual(hdrs["access-control-allow-origin"], origin)
        self.assertEqual(hdrs["access-control-allow-private-network"], "true")
        self.assertEqual(hdrs["access-control-allow-methods"], "POST")
        status, _, hdrs = self.request("POST", "/search", {
            "product_id": "app-a", "version": "2.5", "query": "연결",
        }, headers={"Origin": origin})
        self.assertEqual(status, 200)
        self.assertEqual(hdrs["access-control-allow-origin"], origin)

    def test_same_origin_access_works_without_explicit_allowlist(self):
        origin = f"http://127.0.0.1:{self.server.server_port}"
        status, _, hdrs = self.request("POST", "/search", {
            "product_id": "app-a", "version": "2.5", "query": "연결",
        }, headers={"Origin": origin})
        self.assertEqual(status, 200)
        self.assertEqual(hdrs["access-control-allow-origin"], origin)

    def test_external_browser_origin_cannot_call_any_api(self):
        for origin in ("https://evil.example", "null", "http://127.0.0.1:9999"):
            status, result, hdrs = self.request("POST", "/event", {
                "product_id": "app-a", "error_code": "DB-1001",
            }, headers={"Origin": origin})
            self.assertEqual((status, result["error"]), (403, "origin_not_allowed"))
            self.assertNotIn("access-control-allow-origin", hdrs)
            self.assertEqual(self.request("GET", "/health", headers={"Origin": origin})[0], 403)

    def test_reject_dns_rebinding_host_header(self):
        status, result, _ = self.request("GET", "/health", headers={
            "Host": f"malicious.example:{self.server.server_port}",
        })
        self.assertEqual((status, result["error"]), (403, "invalid_host"))

    def test_reject_unapproved_preflight_methods_or_headers(self):
        base = {"Origin": "https://trusted.example", "Access-Control-Request-Method": "POST"}
        status, result, _ = self.request("OPTIONS", "/chat", headers={
            **base, "Access-Control-Request-Headers": "authorization",
        })
        self.assertEqual((status, result["error"]), (403, "headers_not_allowed"))
        status, result, _ = self.request("OPTIONS", "/chat", headers={
            **base, "Access-Control-Request-Method": "DELETE",
        })
        self.assertEqual((status, result["error"]), (405, "method_not_allowed"))

    def test_invalid_payload_rejected_and_valid_request_still_works(self):
        request = {"product_id": "app-a", "version": "2.5", "query": "연결"}
        for kwargs, code in (
            ({"raw": b"{", "headers": {"Content-Type": "application/json"}}, 400),
            ({"raw": b"[]", "headers": {"Content-Type": "application/json"}}, 400),
            ({"raw": b"hello", "headers": {"Content-Type": "text/plain"}}, 415),
            ({"data": {**request, "secret": "x"}}, 400),
            ({"data": {"product_id": "app-a", "query": "연결", "version": "v1-beta"}}, 400),
            ({"data": {"product_id": "app-a", "query": ""}}, 400),
            ({"data": {"product_id": "app-a", "query": "연결", "version": 2}}, 400),
            ({"data": {"product_id": "app-a", "query": "X" * 40000}}, 413),
        ):
            status, result, _ = self.request("POST", "/search", **kwargs)
            self.assertEqual(status, code, (kwargs, result))
        self.assertEqual(self.request("POST", "/search", request)[0], 200)

    def test_invalid_event_without_identifiers_fails(self):
        status, body, _ = self.request("POST", "/event", {
            "product_id": "app-a",
        })
        self.assertEqual(status, 400)
        self.assertIn("event_id or error_code", body["error"])

    def test_unknown_routes_and_get_are_not_executed(self):
        self.assertEqual(self.request("GET", "/chat")[0], 404)
        self.assertEqual(self.request("POST", "/wrong", {"product_id": "app-a"})[0], 404)


if __name__ == "__main__":
    unittest.main()
