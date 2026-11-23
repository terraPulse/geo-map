// Public identifiers only. Do not put secrets in this file.
// The staging deploy renders config.js from stack outputs. It is not committed.
window.LAYER_MANAGER_CONFIG = {
  authMode: "apigateway-cognito",
  environment: "staging",
  apiBase: "https://example.execute-api.us-west-2.amazonaws.com",
  syntheticFixtures: true,
  signup: false,
  cognito: {
    hostedUiBase: "https://example.auth.us-west-2.amazoncognito.com",
    clientId: "public-app-client-id",
    redirectUri: "https://example.cloudfront.net/"
  },
  effectsNotice: "Saving or publishing changes the registry only. Existing PNG pyramids are not regenerated.",
  tileBackend: {
    baseUrl: null,
    pathOrder: "map",
    integrated: false,
    callsBackend: false,
    publishGeneratesTiles: false
  }
};
