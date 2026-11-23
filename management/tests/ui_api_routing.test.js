const test = require("node:test");
const assert = require("node:assert/strict");
const client = require("../ui/client.js");

const PROD = {
  authMode: "apigateway-cognito",
  apiBase: "https://25iwqj3e92.execute-api.us-west-2.amazonaws.com/",
  signup: false,
  cognito: { clientId: "ig0u0ncar31qpc90h61h24nje" }
};

const PATHS = [
  "/v1/session",
  "/v1/layers?q=",
  "/v1/layers/item?tag=demo%2Fwater",
  "/v1/builds/config",
  "/v1/builds/sources",
  "/v1/builds/plan",
  "/v1/builds/item?job_id=abc",
  "/v1/preview/status",
  "/v1/preview/layers",
  "/v1/preview/tile?order=map&layer_id=fixture%2Fdemo-pyramid&z=2&x=0&y=0"
];

test("production paths stay on the execute-api origin", () => {
  for (const path of PATHS) {
    const url = new URL(client.requestUrl(PROD, path));
    assert.equal(url.origin, "https://25iwqj3e92.execute-api.us-west-2.amazonaws.com");
    assert.equal(url.pathname + url.search, path);
    assert.equal(url.hostname.includes("cloudfront.net"), false);
  }
});

test("cognito mode sends only the bearer token", () => {
  const storage = new Map([["geoMapLayerManagerToken", "access-token"], ["geoMapLayerManagerActor", "fixture-admin"]]);
  storage.getItem = (key) => (storage.has(key) ? storage.get(key) : null);
  const headers = client.authHeaders(PROD, storage);
  assert.equal(headers.authorization, "Bearer access-token");
  assert.equal(headers["x-layer-manager-fixture-actor"], undefined);
});

test("signed-out production mode sends no authorization", () => {
  const storage = { getItem: () => null };
  const headers = client.authHeaders(PROD, storage);
  assert.equal(headers.authorization, undefined);
});

test("xml from the site host is a registry message, not a parser dump", async () => {
  const xml = "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Error><Code>NoSuchKey</Code></Error>";
  const response = {
    ok: false,
    headers: { get: () => "application/xml" },
    text: async () => xml,
    blob: async () => { throw new Error("not an image"); }
  };
  await assert.rejects(
    () => client.parseResponse(response),
    (error) => {
      assert.equal(error.message.includes("Unexpected token"), false);
      assert.equal(error.message.includes("<?xml"), false);
      assert.match(error.message, /registry/i);
      return true;
    }
  );
});

test("a json registry error keeps the server message", async () => {
  const response = {
    ok: false,
    status: 401,
    headers: { get: () => "application/json" },
    text: async () => JSON.stringify({ ok: false, error: { message: "Anonymous access is denied." } })
  };
  await assert.rejects(() => client.parseResponse(response), /Anonymous access is denied/);
});
