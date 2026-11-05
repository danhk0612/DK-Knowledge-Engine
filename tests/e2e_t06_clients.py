"""T06 Windows end-to-end: C# process, real Chrome/Edge, real T05 HTTP API.

Uses a fake LLM for deterministic client tests; no external model download.
Run on Windows GitHub Actions with .NET 8 and Playwright installed.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.localhost_api import KnowledgeHttpServer  # noqa: E402
from builder.knowledge_builder import build  # noqa: E402


class FakeGenerator:
    def generate(self, system: str, user: str) -> str:
        return "DB 서버 포트 3308을 확인하십시오."


class QuietFiles(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".mjs": "text/javascript"}

    def log_message(self, format: str, *args) -> None:
        pass


def start_files() -> ThreadingHTTPServer:
    factory = partial(QuietFiles, directory=str(ROOT / "examples" / "web"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), factory)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def run_csharp(api_port: int) -> None:
    project = ROOT / "examples" / "windows" / "KnowledgeClientExample.csproj"
    def request(product, version, action, *args):
        result = subprocess.run(
            ["dotnet", "run", "--no-build", "--project", str(project), "--",
             str(api_port), product, version, action, *args],
            cwd=ROOT, text=True, capture_output=True, timeout=35,
        )
        assert result.returncode == 0, (result.stdout, result.stderr)
        return json.loads(result.stdout)

    health = request("app-a", "2.5", "health")
    assert health["status"] == "ready"
    assert health["llm_ready"] is True

    search = request("app-a", "2.5", "search", "연결")
    assert [hit["document_id"] for hit in search["results"]] == ["guide-a"], search
    assert search["results"][0]["source_path"] == "app-a/manuals/setup.md", search
    assert request("app-a", "1.5", "search", "연결")["results"] == []
    assert request("app-b", "-", "search", "연결")["results"][0]["document_id"] != "guide-a"

    chat = request("app-a", "2.5", "chat", "연결 오류")
    assert "3308" in chat["answer"] and chat["grounded"] is True, chat
    assert chat["sources"][0]["document_id"] == "guide-a", chat
    assert request("app-a", "2.5", "chat", "블루투스안테나")["grounded"] is False

    event = request("app-a", "2.5", "event", "DB-1001", "connection_failed", "db_settings")
    assert event["matched"] and event["rule_id"] == "db-1001", event
    assert event["source"]["document_id"] == "guide-a", event
    print("C# .NET 8: health/search/chat/event + product/version/source PASS", flush=True)


def run_browser(channel: str, api_port: int, web_port: int, forbidden_port: int) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(channel=channel, headless=True)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(f"http://127.0.0.1:{web_port}/index.html", wait_until="load")
            page.locator("#port").fill(str(api_port))
            page.locator("#product").fill("app-a")
            page.locator("#version").fill("2.5")
            page.locator("#question").fill("연결")

            def click_and_check(action: str) -> str:
                page.locator(f'button[data-action="{action}"]').click()
                page.locator("#status").get_by_text("요청 성공").wait_for(timeout=12000)
                return page.locator("#result").inner_text()

            search = json.loads(click_and_check("search"))
            assert search["results"][0]["document_id"] == "guide-a", search
            assert "app-a/manuals/setup.md" in page.locator("#sources").inner_text()
            assert "9999" not in json.dumps(search, ensure_ascii=False)

            chat = json.loads(click_and_check("chat"))
            assert "3308" in chat["answer"]
            assert chat["sources"][0]["document_id"] == "guide-a"
            assert "app-a/manuals/setup.md" in page.locator("#sources").inner_text()

            page.locator("#error").fill("DB-1001")
            page.locator("#event").fill("connection_failed")
            page.locator("#screen").fill("db_settings")
            event = json.loads(click_and_check("event"))
            assert event["matched"] and event["rule_id"] == "db-1001", event
            assert "app-a/manuals/setup.md" in page.locator("#sources").inner_text()

            health = json.loads(click_and_check("health"))
            assert health["status"] == "ready"

            # A different localhost page origin is deliberately NOT allowlisted.
            denied = context.new_page()
            denied.goto(f"http://127.0.0.1:{forbidden_port}/index.html")
            denied.locator("#port").fill(str(api_port))
            denied.locator("#product").fill("app-a")
            denied.locator("#version").fill("2.5")
            denied.locator("#question").fill("연결")
            denied.locator('button[data-action="search"]').click()
            denied.locator("#status").get_by_text("연결 실패", exact=False).wait_for(timeout=12000)
            assert not denied.locator("#result").inner_text().strip()
            print(f"{channel}: localhost browser CRUD-API and forbidden Origin PASS", flush=True)
            context.close()

            # Diagnostic, not a passing production-website permission test:
            # Browser permission prompting cannot be reliably exercised headlessly.
            # A synthetic HTTPS origin makes this explicit instead of claiming
            # localhost-to-localhost testing validates a real corporate site.
            synthetic = browser.new_context()
            sample = synthetic.new_page()

            def intercept(route):
                filename = "knowledge-client.mjs" if route.request.url.endswith(".mjs") else "index.html"
                media = "text/javascript" if filename.endswith(".mjs") else "text/html"
                route.fulfill(status=200, body=(ROOT / "examples" / "web" / filename).read_bytes(),
                              content_type=media)

            sample.route("https://t06.example.test/**", intercept)
            sample.goto("https://t06.example.test/index.html", wait_until="load")
            sample.locator("#port").fill(str(api_port))
            sample.locator("#product").fill("app-a")
            sample.locator("#version").fill("2.5")
            sample.locator("#question").fill("연결")
            permission_text = sample.locator("#permission").inner_text()
            sample.locator('button[data-action="search"]').click()
            try:
                sample.locator("#status").get_by_text(
                    "요청 성공", exact=True
                ).wait_for(timeout=3500)
                result = "granted"
            except Exception:
                result = sample.locator("#status").inner_text()
            print(f"{channel}: synthetic HTTPS public-origin LNA diagnostic: "
                  f"permission={permission_text!r}, outcome={result!r}", flush=True)
            synthetic.close()
        finally:
            browser.close()


def main() -> None:
    with tempfile.TemporaryDirectory() as dirname:
        tmp = Path(dirname)
        root = tmp / "sources"
        a = root / "app-a" / "manuals"
        b = root / "app-b" / "manuals"
        rules = root / "app-a" / "rules"
        for path in (a, b, rules):
            path.mkdir(parents=True, exist_ok=True)
        (a / "setup.md").write_text(
            "# DB 연결 오류\n\n연결 오류 발생 시 서버 포트 3308을 확인하십시오.", encoding="utf-8"
        )
        (a / "setup.md.meta.json").write_text(json.dumps({
            "document_id": "guide-a", "version_from": "2.0", "version_to": "3.0"
        }), encoding="utf-8")
        (b / "guide.txt").write_text("연결 오류 발생 시 서버 포트 9999를 확인하십시오.",
                                     encoding="utf-8")
        (rules / "db.json").write_text(json.dumps({
            "rule_id": "db-1001", "product_id": "app-a",
            "event_id": "connection_failed", "error_code": "DB-1001",
            "screen_id": "db_settings", "document_id": "guide-a",
            "title": "연결 실패", "content": "포트 3308을 확인하십시오."
        }, ensure_ascii=False), encoding="utf-8")
        db = tmp / "knowledge.db"
        build(root, db)
        web = start_files()
        forbidden = start_files()
        api = KnowledgeHttpServer(
            db, port=0, generator=FakeGenerator(),
            allowed_origins=(
                f"http://127.0.0.1:{web.server_port}",
                "https://t06.example.test",
            ),
        )
        server_thread = threading.Thread(target=api.serve_forever, daemon=True)
        server_thread.start()
        try:
            run_csharp(api.server_port)
            for browser in ("chrome", "msedge"):
                run_browser(browser, api.server_port, web.server_port, forbidden.server_port)
        finally:
            api.shutdown()
            api.server_close()
            server_thread.join(timeout=3)
            for server in (web, forbidden):
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    main()
