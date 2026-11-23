import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "/tmp/ui-proof/node_modules/puppeteer-core/lib/esm/puppeteer/puppeteer-core.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../ui");
const api = "https://25iwqj3e92.execute-api.us-west-2.amazonaws.com";
const out = "/opt/cursor/artifacts/ui-prod-proof";
fs.mkdirSync(out, { recursive: true });

const config = `window.LAYER_MANAGER_CONFIG = ${JSON.stringify({
  authMode: "apigateway-cognito",
  environment: "staging",
  apiBase: api,
  syntheticFixtures: false,
  signup: false,
  cognito: {
    hostedUiBase: "https://example.auth.us-west-2.amazoncognito.com",
    clientId: "ig0u0ncar31qpc90h61h24nje",
    redirectUri: "http://127.0.0.1/"
  }
})};`;

const types = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml" };
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");
  if (url.pathname === "/config.js") {
    res.writeHead(200, { "content-type": "text/javascript" });
    res.end(config);
    return;
  }
  const file = path.join(root, url.pathname === "/" ? "index.html" : url.pathname);
  if (!file.startsWith(root) || !fs.existsSync(file)) {
    res.writeHead(404, { "content-type": "application/xml" });
    res.end("<?xml version=\"1.0\" encoding=\"UTF-8\"?><Error><Code>NoSuchKey</Code></Error>");
    return;
  }
  res.writeHead(200, { "content-type": types[path.extname(file)] || "text/plain" });
  res.end(fs.readFileSync(file));
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const port = server.address().port;
const pageOrigin = `http://127.0.0.1:${port}`;
const calls = [];

function json(result) {
  return JSON.stringify({ ok: true, result });
}

const routes = {
  "/v1/session": json({
    actor: { sub: "user", username: "operator", role: "layer-admin", synthetic_identity: false, auth_mode: "apigateway-cognito" },
    banner: "Signed in through the staging Cognito pool. Records badged synthetic are fixtures.",
    effects_notice: "Saving or publishing changes the registry only. Existing PNG pyramids are not regenerated.",
    tile_backend: { note: "", integration_status: "unconfigured" }
  }),
  "/v1/layers": json({
    layers: [{ tag: "demo/water_freq/y2025", title: "Synthetic water frequency", backend: "png-pyramid", status: "published", synthetic: true }],
    inventory_note: "Every layer in this result is a labeled synthetic fixture. This is not the live tile inventory."
  }),
  "/v1/builds/config": json({ real_builds_enabled: false, executor: "disabled", note: "Real builds stay off.", batch_size: 32, absolute_max: 256 }),
  "/v1/builds/sources": json({ sources: [] }),
  "/v1/preview/status": json({ enabled: false, pending: true, note: "Renderer preview is unconfigured. The test function is not called." })
};

const browser = await puppeteer.launch({
  executablePath: "/usr/local/bin/google-chrome",
  headless: "new",
  args: ["--no-sandbox", "--disable-dev-shm-usage"]
});
const page = await browser.newPage();
await page.setRequestInterception(true);
page.on("request", (request) => {
  const url = new URL(request.url());
  calls.push({ method: request.method(), url: request.url(), headers: request.headers() });
  if (url.origin === pageOrigin) {
    request.continue();
    return;
  }
  if (url.origin !== api) {
    request.abort();
    return;
  }
  const cors = {
    "access-control-allow-origin": pageOrigin,
    "access-control-allow-headers": "authorization, content-type, accept",
    "access-control-allow-methods": "GET, POST, PATCH, OPTIONS",
    "content-type": "application/json"
  };
  if (request.method() === "OPTIONS") {
    request.respond({ status: 204, headers: cors, body: "" });
    return;
  }
  const key = url.pathname;
  const body = routes[key];
  if (!body) {
    request.respond({ status: 404, headers: cors, body: json(null) });
    return;
  }
  request.respond({ status: 200, headers: cors, body });
});

function dataCalls() {
  return calls.filter((call) => call.url.startsWith(api) && call.method !== "OPTIONS");
}

await page.setViewport({ width: 1280, height: 800 });
await page.goto(pageOrigin + "/", { waitUntil: "networkidle0" });
if (dataCalls().length) throw new Error("API was called before sign-in: " + JSON.stringify(dataCalls()));
await page.screenshot({ path: path.join(out, "desktop-signin.png") });
await page.setViewport({ width: 390, height: 844 });
await page.screenshot({ path: path.join(out, "mobile-signin.png") });

await page.setViewport({ width: 1280, height: 800 });
await page.evaluate(() => sessionStorage.setItem("geoMapLayerManagerToken", "test-access-token"));
await page.reload({ waitUntil: "networkidle0" });
await page.waitForSelector("table");
const session = dataCalls().find((call) => call.url.startsWith(api + "/v1/session"));
const layers = dataCalls().find((call) => call.url.startsWith(api + "/v1/layers"));
if (!session || session.headers.authorization !== "Bearer test-access-token") throw new Error("session auth missing");
if (!layers || layers.headers.authorization !== "Bearer test-access-token") throw new Error("layers auth missing");
if (dataCalls().some((call) => new URL(call.url).origin !== api)) throw new Error("data call left the API origin");
await page.screenshot({ path: path.join(out, "desktop-layers.png") });

page.on("pageerror", (error) => console.log("PAGEERROR", error.message));
page.on("console", (msg) => console.log("CONSOLE", msg.type(), msg.text()));
await page.click("#nav-build");
try {
  await page.waitForFunction(() => /Builds off/i.test(document.body.innerText) || document.body.innerText.includes("registry did not answer"), { timeout: 5000 });
} catch (error) {
  console.log("DATASETS TEXT", await page.evaluate(() => document.body.innerText));
  console.log("CALLS", JSON.stringify(calls.map((call) => call.method + " " + call.url), null, 2));
  throw error;
}
if (documentBodyIncludesXml(await page.evaluate(() => document.body.innerText))) throw new Error("datasets still shows a parser exception");
const configCall = dataCalls().find((call) => call.url === api + "/v1/builds/config");
const sourceCall = dataCalls().find((call) => call.url === api + "/v1/builds/sources");
if (!configCall || configCall.headers.authorization !== "Bearer test-access-token") throw new Error("builds/config was not sent to the API with Authorization");
if (!sourceCall || sourceCall.headers.authorization !== "Bearer test-access-token") throw new Error("builds/sources was not sent to the API with Authorization");
await page.screenshot({ path: path.join(out, "desktop-datasets.png") });

await page.click("#nav-preview");
await page.waitForFunction(() => document.body.innerText.includes("Preview is not configured") || document.body.innerText.includes("registry did not answer"));
const preview = dataCalls().find((call) => call.url === api + "/v1/preview/status");
if (!preview || preview.headers.authorization !== "Bearer test-access-token") throw new Error("preview/status missed the API");
await page.screenshot({ path: path.join(out, "desktop-preview.png") });

await page.setViewport({ width: 390, height: 844 });
await page.click("#nav-layers");
await page.waitForSelector("table");
const width = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, inner: window.innerWidth }));
if (width.scroll > width.inner + 1) throw new Error("mobile overflow " + JSON.stringify(width));
await page.screenshot({ path: path.join(out, "mobile-layers.png") });
await page.click("#nav-build");
await page.waitForFunction(() => /Builds off/i.test(document.body.innerText));
await page.screenshot({ path: path.join(out, "mobile-datasets.png") });

await browser.close();
server.close();
console.log(JSON.stringify({ ok: true, calls: dataCalls().map((call) => call.method + " " + call.url), width }, null, 2));

function documentBodyIncludesXml(text) {
  return text.includes("Unexpected token") || text.includes("<?xml");
}
