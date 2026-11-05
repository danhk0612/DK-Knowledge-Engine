// No external libraries or network services other than the explicitly local API.
const API_BASE = "http://127.0.0.1:8765";

async function request(path, body) {
  const options = body === undefined
    ? { method: "GET" }
    : {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      };

  // Chrome/Edge LNA: HTTPS pages explicitly target this PC's loopback API.
  // This does not override user or enterprise network permissions.
  options.targetAddressSpace = "loopback";
  const response = await fetch(API_BASE + path, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error ?? "HTTP " + response.status);
  }
  return data;
}

export function health() {
  return request("/health");
}

export function searchHelp(productId, version, query) {
  return request("/search", { product_id: productId, version: version || null, query });
}

export function askHelp(productId, version, question) {
  return request("/chat", { product_id: productId, version: version || null, question });
}

export function eventHelp(productId, version, eventId, errorCode, screenId) {
  return request("/event", {
    product_id: productId,
    version: version || null,
    event_id: eventId || null,
    error_code: errorCode || null,
    screen_id: screenId || null,
  });
}
