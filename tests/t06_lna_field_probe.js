/*
 * DK Knowledge Engine — operator-invoked LNA field probe.
 * Paste this file into DevTools Console on an AUTHORIZED HTTPS intranet page.
 * It adds one temporary button. Only a user click starts any network request.
 * It never sends information anywhere except http://127.0.0.1:8765.
 * The console report contains no questions, answers, source paths or site URL.
 */
(() => {
  "use strict";
  const buttonId = "dk-knowledge-lna-field-probe";
  const baseUrl = "http://127.0.0.1:8765";
  if (document.getElementById(buttonId)) {
    console.info("DK_LNA_FIELD_PROBE: already installed; click the existing test button.");
    return;
  }

  const button = document.createElement("button");
  button.id = buttonId;
  button.type = "button";
  button.textContent = "DK 로컬 API 연결 검사";
  button.style.cssText = "position:fixed;bottom:16px;right:16px;z-index:2147483647;padding:10px;background:#222;color:#fff;border:1px solid #aaa;border-radius:6px;font:14px sans-serif;cursor:pointer";

  async function networkCheck(path, options, expectedField) {
    try {
      const response = await fetch(baseUrl + path, options);
      if (!response.ok) return { result: "http_error", status: response.status };
      // Do not expose or log response bodies, including customer manual text.
      const body = await response.json();
      const valid = expectedField === "status"
        ? body && typeof body.status === "string" && typeof body.llm_ready === "boolean"
        : body && Array.isArray(body.results);
      return valid ? { result: "ok", status: response.status }
        : { result: "unexpected_json", status: response.status };
    } catch (error) {
      // TypeError can mean LNA, CSP, CORS, mixed content, or API unavailable.
      return { result: "fetch_rejected", error_type: error && error.name === "AbortError" ? "AbortError" : "TypeError_or_network" };
    }
  }

  async function permissionState() {
    if (!navigator.permissions || !navigator.permissions.query) return "unsupported";
    try {
      const result = await navigator.permissions.query({ name: "loopback-network" });
      return result.state;
    } catch {
      return "unsupported";
    }
  }

  button.addEventListener("click", async () => {
    button.disabled = true;
    button.textContent = "로컬 연결 검사 중…";
    const report = {
      schema_version: 1,
      timestamp_utc: new Date().toISOString(),
      origin_scheme: location.protocol,
      secure_context: Boolean(globalThis.isSecureContext),
      permission_after: "not_checked",
      health: { result: "not_run" },
      search: { result: "not_run" },
    };
    try {
      if (report.origin_scheme !== "https:" || !report.secure_context) {
        report.note = "Run only from an authorized HTTPS secure context";
      } else {
        // Start fetch in the click handler BEFORE any awaited operation so
        // a browser LNA permission prompt is associated with user activation.
        report.health = await networkCheck("/health", {
          method: "GET", targetAddressSpace: "loopback",
        }, "status");
        if (report.health.result === "ok") {
          report.search = await networkCheck("/search", {
            method: "POST", targetAddressSpace: "loopback",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              product_id: "example-program", version: "2.1.0", query: "연결 오류",
            }),
          }, "results");
        }
      }
      report.permission_after = await permissionState();
      report.all_requests_ok = report.health.result === "ok" && report.search.result === "ok";
      button.textContent = report.all_requests_ok ? "DK 로컬 API 정상 (콘솔 확인)" : "DK 검사 결과 확인 (콘솔)";
      console.info("DK_LNA_FIELD_PROBE_RESULT", JSON.stringify(report));
    } finally {
      button.disabled = false;
    }
  });
  document.body.appendChild(button);
  console.info("DK_LNA_FIELD_PROBE: temporary button installed; click it to request loopback permission and test. To remove: document.getElementById('dk-knowledge-lna-field-probe')?.remove()");
})();