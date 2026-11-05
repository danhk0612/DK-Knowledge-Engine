// Chromium end-to-end tests: actual cross-origin browser fetches to T05.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { chromium } from "playwright";

const fixture = spawn("python", ["-u", "tests/t06_fixture.py", "--web"], {
  cwd: process.cwd(),
  env: { ...process.env, PYTHONPATH: "." },
  stdio: ["ignore", "pipe", "pipe"],
});
let output = "";
fixture.stdout.setEncoding("utf8");
fixture.stderr.setEncoding("utf8");
fixture.stdout.on("data", (data) => { output += data; });
fixture.stderr.on("data", (data) => { output += data; });

async function ready() {
  const limit = Date.now() + 30000;
  while (!output.includes("T06_FIXTURE_READY")) {
    if (fixture.exitCode !== null) throw new Error("fixture failed: " + output);
    if (Date.now() > limit) throw new Error("fixture startup timeout: " + output);
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
}

async function waitResult(page, substring) {
  await page.waitForFunction(
    (text) => document.getElementById("result")?.textContent.includes(text),
    substring,
    { timeout: 15000 },
  );
}

let browser;
try {
  await ready();
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto("http://127.0.0.1:8766/");
  await page.locator("#health").click();
  await waitResult(page, "엔진: ready");
  await page.locator("#search").click();
  await waitResult(page, "3308");
  assert.match(await page.locator("#sources").innerText(), /example-program\/manuals\/setup\.md/);
  // Embedded markup from a retrieved manual must be plain text, not executable HTML.
  assert.equal(await page.locator("#result img").count(), 0);
  await page.locator("#chat").click();
  await waitResult(page, "DB 서버 포트 3308");
  assert.match(await page.locator("#sources").innerText(), /setup\.md/);
  await page.locator("#event-help").click();
  await waitResult(page, "데이터베이스 연결 오류");
  assert.match(await page.locator("#sources").innerText(), /setup\.md/);

  // Same webpage content on an unlisted origin cannot use the local API.
  const blocked = await browser.newPage();
  await blocked.goto("http://127.0.0.1:8767/");
  await blocked.locator("#search").click();
  await waitResult(blocked, "요청 실패:");
  assert.equal(await blocked.locator("#sources").innerText(), "");
  // Virtual HTTPS origin: serve the existing page and JS via Playwright routing,
  // without contacting an intranet, creating TLS certificates, or bypassing CORS.
  // This covers secure-context HTTPS -> real 127.0.0.1 HTTP API, but the
  // browser permission is granted in CI and is NOT a customer policy test.
  const httpsOrigin = "https://intranet.example";
  const httpsContext = await browser.newContext();
  await httpsContext.grantPermissions(["local-network-access"], { origin: httpsOrigin });
  await httpsContext.route(httpsOrigin + "/**", async (route) => {
    const routePath = new URL(route.request().url()).pathname;
    const file = routePath === "/" ? "index.html" : routePath.slice(1);
    if (!["index.html", "app.js", "api-client.js"].includes(file)) {
      await route.fulfill({ status: 404, body: "Not found" });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: file.endsWith(".html") ? "text/html; charset=utf-8" : "text/javascript; charset=utf-8",
      body: readFileSync(new URL("../integrations/web/" + file, import.meta.url)),
    });
  });
  const securePage = await httpsContext.newPage();
  await securePage.goto(httpsOrigin + "/");
  assert.equal(await securePage.evaluate(() => globalThis.isSecureContext), true);
  await securePage.locator("#health").click();
  await waitResult(securePage, "엔진: ready");
  await securePage.locator("#search").click();
  await waitResult(securePage, "3308");
  assert.match(await securePage.locator("#sources").innerText(), /example-program\\/manuals\\/setup\\.md/);
  await httpsContext.close();
  console.log("T06 virtual HTTPS-origin -> real localhost API OK: health/search, CORS and secure context");

  console.log("T06 Chromium browser integration OK: health/search/chat/event, source, blocked origin");
} finally {
  if (browser) await browser.close();
  fixture.kill();
}
