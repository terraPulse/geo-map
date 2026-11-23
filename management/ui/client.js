(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.LayerManagerClient = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function apiOrigin(config) {
    const base = String((config && config.apiBase) || "").replace(/\/$/, "");
    if (!base) return "";
    const url = new URL(base);
    if (url.protocol !== "https:" && url.hostname !== "127.0.0.1" && url.hostname !== "localhost") {
      throw new Error("The registry API address must use https.");
    }
    return url.origin;
  }

  function requestUrl(config, path) {
    if (typeof path !== "string" || path.charAt(0) !== "/" || path.indexOf("//") === 0) {
      throw new Error("A registry request must use an API path.");
    }
    const origin = apiOrigin(config);
    return origin ? origin + path : path;
  }

  function authHeaders(config, storage) {
    const headers = { accept: "application/json", "content-type": "application/json" };
    if (config && config.authMode === "local-fixture") {
      const name = storage.getItem("geoMapLayerManagerActor");
      if (name) headers["x-layer-manager-fixture-actor"] = name;
      return headers;
    }
    const token = storage.getItem("geoMapLayerManagerToken");
    if (token) headers.authorization = "Bearer " + token;
    return headers;
  }

  async function parseResponse(response) {
    const type = (response.headers.get("content-type") || "").toLowerCase();
    if (type.indexOf("image/png") === 0) {
      if (!response.ok) throw new Error("The preview image could not be loaded.");
      return { kind: "png", value: await response.blob() };
    }
    const text = await response.text();
    const trimmed = text.trim();
    if (!trimmed || trimmed.charAt(0) === "<" || type.indexOf("xml") !== -1 || type.indexOf("html") !== -1) {
      throw new Error("The registry did not answer this request. The site received a web error page instead of registry data.");
    }
    let payload;
    try {
      payload = JSON.parse(text);
    } catch (error) {
      throw new Error("The registry answer could not be read.");
    }
    if (!response.ok || payload.ok === false) {
      const error = new Error((payload.error && payload.error.message) || "The registry request failed.");
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return { kind: "json", value: payload.result };
  }

  async function request(config, storage, fetchImpl, method, path, body) {
    const response = await fetchImpl(requestUrl(config, path), {
      method: method,
      headers: authHeaders(config, storage),
      body: body == null ? undefined : JSON.stringify(body)
    });
    const parsed = await parseResponse(response);
    return parsed.value;
  }

  return { apiOrigin, requestUrl, authHeaders, parseResponse, request };
});
