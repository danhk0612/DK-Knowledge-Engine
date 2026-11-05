import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { test } from "node:test";
import { runInNewContext } from "node:vm";

const script = readFileSync(new URL("./t06_lna_field_probe.js", import.meta.url), "utf8");

function contextFactory({ allow = true, scheme = "https:", secure = true } = {}) {
  const handlers = {};
  const calls = [];
  const logs = [];
  const document = {
    getElementById: () => null,
    createElement: () => ({ style: {}, addEventListener: (name, handler) => { handlers[name] = handler; } }),
    body: { appendChild: () => {} },
  };
  const scope = {
    document,
    location: { protocol: scheme },
    navigator: { permissions: { query: async ({ name }) => { assert.equal(name, "loopback-network"); return { state: allow ? "granted" : "denied" }; } } },
    isSecureContext: secure,
    fetch: async (url, options) => {
      calls.push({ url, options });
      if (!allow) throw new TypeError("permission denied");
      return { ok: true, status: 200, json: async () => url.endsWith("/health") ? { status: "ready", llm_ready: true } : { results: [] } };
    },
    console: { info: (...args) => logs.push(args) },
    Date, JSON,
  };
  scope.globalThis = scope;
  runInNewContext(script, scope);
  return { handlers, calls, logs };
}

function reportOf(logs) {
  const entry = logs.find(([name]) => name === "DK_LNA_FIELD_PROBE_RESULT");
  assert.ok(entry);
  return JSON.parse(entry[1]);
}

test("no requests until real button click; secure HTTPS success uses only localhost", async () => {
  const { handlers, calls, logs } = contextFactory();
  assert.equal(calls.length, 0);
  await handlers.click();
  const report = reportOf(logs);
  assert.equal(report.all_requests_ok, true);
  assert.equal(report.permission_after, "granted");
  assert.deepEqual(calls.map(c => c.url), ["http://127.0.0.1:8765/health", "http://127.0.0.1:8765/search"]);
  assert.equal(calls[0].options.targetAddressSpace, "loopback");
  assert.equal(calls[1].options.targetAddressSpace, "loopback");
  assert.equal(calls[1].options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(calls[1].options.body), { product_id: "example-program", version: "2.1.0", query: "연결 오류" });
  assert.ok(!JSON.stringify(report).includes("연결 오류"));
});

test("insecure top-level page performs no network requests", async () => {
  const { handlers, calls, logs } = contextFactory({ scheme: "http:", secure: false });
  await handlers.click();
  assert.equal(calls.length, 0);
  assert.equal(reportOf(logs).all_requests_ok, false);
});

test("rejected permission keeps HTTP search disabled and exposes no server data", async () => {
  const { handlers, calls, logs } = contextFactory({ allow: false });
  await handlers.click();
  assert.equal(calls.length, 1);
  const report = reportOf(logs);
  assert.equal(report.health.result, "fetch_rejected");
  assert.equal(report.search.result, "not_run");
  assert.equal(report.permission_after, "denied");
});