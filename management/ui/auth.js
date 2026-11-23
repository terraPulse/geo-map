(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.LayerManagerAuth = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function randomVerifier() {
    const bytes = new Uint8Array(32);
    crypto.getRandomValues(bytes);
    return base64Url(bytes);
  }

  function base64Url(bytes) {
    let text = "";
    const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    for (let i = 0; i < view.length; i += 1) {
      text += String.fromCharCode(view[i]);
    }
    return btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  }

  async function challengeS256(verifier) {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
    return base64Url(digest);
  }

  function hostedUiUrl(cognito, redirectUri, state, challenge) {
    const url = new URL(cognito.hostedUiBase + "/oauth2/authorize");
    url.searchParams.set("response_type", "code");
    url.searchParams.set("client_id", cognito.clientId);
    url.searchParams.set("redirect_uri", redirectUri);
    url.searchParams.set("scope", "openid email profile");
    url.searchParams.set("code_challenge_method", "S256");
    url.searchParams.set("code_challenge", challenge);
    url.searchParams.set("state", state);
    return url.toString();
  }

  return { randomVerifier, challengeS256, hostedUiUrl, base64Url };
});
