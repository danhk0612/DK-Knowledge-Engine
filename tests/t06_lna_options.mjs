// Validate the browser integration's explicit loopback target and unchanged API contract.
// A mocked fetch is enough for this options contract; real Chromium calls are
// covered by t06_browser.mjs. This test does not claim enterprise LNA permission.
import assert from "node:assert/strict";
import { test } from "node:test";

test("all four API methods declare a loopback target without changing requests", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, status: 200, json: async () => ({ status: "ready" }) };
  };
  try {
    const { health, searchHelp, askHelp, eventHelp } = await import("../integrations/web/api-client.js");
    await health();
    await searchHelp("example-program", "2.1.0", "연결 오류");
    await askHelp("example-program", "2.1.0", "어떤 포트?");
    await eventHelp("example-program", "2.1.0", "connection_failed", "DB-1001", "db_settings");

    assert.deepEqual(calls.map(({ url }) => url), [
      "http://127.0.0.1:8765/health",
      "http://127.0.0.1:8765/search",
      "http://127.0.0.1:8765/chat",
      "http://127.0.0.1:8765/event",
    ]);
    assert.deepEqual(calls.map(({ options }) => options.method), ["GET", "POST", "POST", "POST"]);
    for (const { options } of calls) {
      assert.equal(options.targetAddressSpace, "loopback");
    }
    const payloads = calls.slice(1).map(({ options }) => {
      assert.equal(options.headers["Content-Type"], "application/json");
      return JSON.parse(options.body);
    });
    assert.deepEqual(payloads, [
      { product_id: "example-program", version: "2.1.0", query: "연결 오류" },
      { product_id: "example-program", version: "2.1.0", question: "어떤 포트?" },
      {
        product_id: "example-program", version: "2.1.0", event_id: "connection_failed",
        error_code: "DB-1001", screen_id: "db_settings",
      },
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
