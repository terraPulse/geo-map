# Security review

This increment was not deployed. No AWS credentials were used.

## Controls in the template and the API

- Every `/v1` route requires an API Gateway JWT authorizer. The Lambda rejects a missing authorizer context, a wrong issuer, a wrong client id, a bad `token_use`, a missing or expired `exp`, and a user who is not in `layer-admin` or `layer-reader`.
- There is no public data route. `/ready` exists only on the local process and returns no layer data. It is not in the HTTP API.
- Cognito self-signup is off. MFA is a required software token. The template creates groups and no users, so it sends no invitation.
- The app client has no secret. The browser uses authorization code and PKCE. Tokens stay in `sessionStorage`.
- The Lambda role is limited to item operations on the new table and writes to its own log group. It has no `s3:*`, no `dynamodb:DeleteItem`, and no `dynamodb:Scan`.
- The console bucket is private. CloudFront uses origin access control. The bucket policy allows `s3:GetObject` only from that distribution.
- CORS allows one origin: the new CloudFront domain. It is not `*`.
- Logs retain 14 days. The access-log format does not include the authorization header or JWT claims.
- Fixture identities work only when `LAYER_MANAGER_ENV` is `local` or `test` and fixture auth is explicitly allowed. Staging refuses them.
- `LAYER_MANAGER_ENV=prod` is refused.
- Tile preview does not fetch URLs. The admin token is not attached to a tile host. Production tile hosts and `map-tiles-dev` are rejected as the configured base URL.
- Registry writes cannot set `png_pyramid_regenerated_on_write` to true.

## Residual gaps

1. The Lambda trusts API Gateway for the JWT signature and then re-checks claims. It does not download the Cognito JWKS itself. Invoke permission is limited to this API and this stack's CloudFormation seed. A principal who can `lambda:InvokeFunction` with a forged event could skip the signature check.
2. The HTTP API execute-api hostname stays reachable. Calls without a valid Cognito token receive 401 and no layer data. Disabling that hostname requires a custom domain, which this stack does not create.
3. `connect-src` allows `https://*.execute-api.us-west-2.amazonaws.com` so the console can reach this API without a circular template reference. CORS still allows only the CloudFront origin. A stolen admin token could be presented to another execute-api in the region; that API would have to accept this user pool.
4. No WAF. Throttling is 10 requests per second, burst 20. WAF has a monthly charge and was left out.
5. Encryption is SSE-S3 and DynamoDB's owned key. A customer-managed key would add about one dollar per month and was left out.
6. CloudFront standard access logs are not enabled. Lambda and API Gateway logs are. The legacy S3 ACL log-delivery path fights the public-access block.
7. Deleting the stack fails while the frontend or artifact bucket still has objects. Empty only the buckets named by the stack outputs. The application role cannot delete those objects.
8. The seed function and the API share a role that includes `dynamodb:PutItem`. Seed uses a condition that skips existing tags. A defect in the seed code could still write rows. It cannot write another table.
9. Synthetic fixtures are the initial catalog. They are badged. They are not the live inventory. Stack deletion removes them with the table.
10. Import of a real production `setting.ini` is blocked when the text names `geo-map-tiles` or `admin.terrapulse.com`. Cataloging real layers needs a later, reviewed change to that guard.
11. The performance-branch test Lambda is not deployed and not called. Coupling is an address template only, and only after the parent sets `TileBackendBaseUrl`.
