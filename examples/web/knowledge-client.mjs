/** T06 browser client for the T05 same-PC API; no dependencies. */
export class KnowledgeClient {
  constructor(port = 8765) {
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
      throw new RangeError("port must be between 1 and 65535");
    }
    this.baseUrl = `http://127.0.0.1:${port}`;
  }

  async request(path, data) {
    const options = {
      method: data === undefined ? "GET" : "POST",
      mode: "cors",
      credentials: "omit",
      cache: "no-store",
      // This lets Chromium verify the intended loopback address space.
      targetAddressSpace: "loopback",
    };
    if (data !== undefined) {
      options.headers = { "Content-Type": "application/json" };
      options.body = JSON.stringify(data);
    }
    const response = await fetch(this.baseUrl + path, options);
    const json = await response.json();
    if (!response.ok) {
      const error = new Error(json.error || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return json;
  }

  health() {
    return this.request("/health");
  }

  search(productId, query, version) {
    return this.request("/search", {
      product_id: productId,
      query,
      ...(version ? { version } : {}),
    });
  }

  chat(productId, question, version) {
    return this.request("/chat", {
      product_id: productId,
      question,
      ...(version ? { version } : {}),
    });
  }

  event(productId, errorCode, eventId, screenId, version) {
    return this.request("/event", {
      product_id: productId,
      ...(version ? { version } : {}),
      ...(errorCode ? { error_code: errorCode } : {}),
      ...(eventId ? { event_id: eventId } : {}),
      ...(screenId ? { screen_id: screenId } : {}),
    });
  }
}

/** Query Chrome's granular LNA permission; never query the legacy alias. */
export async function loopbackPermissionState() {
  if (!navigator.permissions?.query) return "unavailable";
  try {
    const status = await navigator.permissions.query({ name: "loopback-network" });
    return status.state;
  } catch {
    // Older browsers may not expose this permission type.
    return "unavailable";
  }
}
