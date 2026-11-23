# CORS preflight hotfix

Live check on the deployed baseline (`c12db1d`, stack create complete): a full browser preflight to `https://25iwqj3e92.execute-api.us-west-2.amazonaws.com/v1/layers` and `/v1/layers/item` returned **401**. The response already had the console origin in `Access-Control-Allow-Origin` and the expected method and header lists. A browser still treats a non-2xx preflight as a failure, so the bearer GET/POST never runs.

## Why

`ANY /v1/{proxy+}` requires the JWT authorizer. `OPTIONS` is one of the methods `ANY` matches. API Gateway attached the configured CORS headers to that 401, but it did not skip the authorizer. A preflight has no bearer token, so the authorizer returns 401.

This was observed with all three preflight headers set: `Origin`, `Access-Control-Request-Method` (`GET`, `POST`, or `PATCH`), and `Access-Control-Request-Headers: authorization,content-type`. It is not only the incomplete OPTIONS case.

## Change

One new route, and the function returns 204 before it checks a JWT:

| Resource | Action | Notes |
| --- | --- | --- |
| `OptionsRoute` (`AWS::ApiGatewayV2::Route`) | Create | `OPTIONS /v1/{proxy+}`, `AuthorizationType: NONE`, same Lambda integration |
| `ApiFunction` | Update code | OPTIONS under `/v1/` returns 204 or 403 and no registry body |
| `ApiRoute` | Unchanged | `ANY /v1/{proxy+}` stays JWT |
| Cognito user pool, client, domain | Unchanged | Do not pass a different `CognitoDomainPrefix` |
| Buckets, distribution, DynamoDB table | Unchanged | No replacement |

`EnableBuilds` stays `false`. `RendererInvokeEnabled` stays `false`. No users are created.

A matching preflight requires the origin to equal the configured console origin exactly, the requested method to be GET, POST, PATCH, or OPTIONS, and any requested headers to be only `authorization` and `content-type`. Any other origin, method, or header is 403 and the response does not echo that origin. GET and POST without a JWT stay 401.

## Executor check after the update

Do not run these from the implementation agent.

```bash
API=https://25iwqj3e92.execute-api.us-west-2.amazonaws.com
ORIGIN=https://d1p7xtlh8zwywg.cloudfront.net
for method in GET POST PATCH; do
  curl -sS -D - -o /tmp/preflight-body \
    -X OPTIONS "$API/v1/layers" \
    -H "Origin: $ORIGIN" \
    -H "Access-Control-Request-Method: $method" \
    -H "Access-Control-Request-Headers: authorization,content-type"
done
curl -sS -D - -o /tmp/preflight-item \
  -X OPTIONS "$API/v1/layers/item" \
  -H "Origin: $ORIGIN" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization,content-type"
curl -sS -D - -o /tmp/bad-origin \
  -X OPTIONS "$API/v1/layers" \
  -H "Origin: https://evil.example" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
curl -sS -D - -o /tmp/anon \
  -H "Origin: $ORIGIN" \
  "$API/v1/layers"
```

Expect the matching OPTIONS calls to be 204 (or another 2xx) with exactly one `Access-Control-Allow-Origin: https://d1p7xtlh8zwywg.cloudfront.net`. Expect the evil origin to have no allow-origin header. Expect the anonymous GET to stay 401.

If a 204 contains two `Access-Control-Allow-Origin` values, stop and report that. API Gateway may also add the header it already adds to the 401. The function sets the same single origin so a browser preflight can succeed when the gateway does not replace a 401.

## Update command

Profile `tp`, region `us-west-2`, stack `geo-map-layer-manager-staging`. Upload the new zip to the existing artifact bucket under a new key. Pass the same Cognito prefix the stack already uses.

```bash
aws cloudformation deploy \
  --profile tp --region us-west-2 \
  --stack-name geo-map-layer-manager-staging \
  --template-file template.yaml \
  --parameter-overrides \
    ArtifactKey=lambda/layer-manager-cors.zip \
    CognitoDomainPrefix=tp-geomap-layers-544020760996 \
    TileBackendBaseUrl= \
    RendererInvokeEnabled=false \
    EnableBuilds=false \
  --no-execute-changeset
```

Read the changeset. The only new resource should be `OptionsRoute`. `ApiFunction` should be an update, not a replacement. The user pool, client, distribution, buckets, and registry table should not be replaced. Then deploy the changeset.
