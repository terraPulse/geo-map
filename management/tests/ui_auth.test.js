const test = require("node:test");
const assert = require("node:assert/strict");
const auth = require("../ui/auth.js");

test("pkce challenge is base64url sha256 without padding", async () => {
  const challenge = await auth.challengeS256("fixture-verifier-value");
  assert.equal(challenge.includes("="), false);
  assert.equal(challenge.includes("+"), false);
  assert.equal(challenge.includes("/"), false);
  const again = await auth.challengeS256("fixture-verifier-value");
  assert.equal(challenge, again);
});

test("hosted UI url uses code and S256 and does not embed a client secret", () => {
  const url = new URL(auth.hostedUiUrl(
    { hostedUiBase: "https://example.auth.us-west-2.amazoncognito.com", clientId: "public-client" },
    "https://d111111abcdef8.cloudfront.net/",
    "state-1",
    "challenge-1"
  ));
  assert.equal(url.searchParams.get("response_type"), "code");
  assert.equal(url.searchParams.get("code_challenge_method"), "S256");
  assert.equal(url.searchParams.get("client_secret"), null);
});
