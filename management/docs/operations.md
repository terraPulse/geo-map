# Staging deploy and rollback

Do not run these commands from the implementation agent. The parent readiness executor runs them after review, with profile `mfeng`, region `us-west-2`, and account `544020760996`. Do not use profile `6g`. Do not change `admin.terrapulse.com`, existing APIs, DNS, or tile buckets.

Nothing here creates a Cognito user or sends an invitation. The pool starts empty. The first admin is enrolled later, by the parent, for the owner's confirmed identity.

## Identity preflight

```bash
export AWS_PROFILE=mfeng
export AWS_REGION=us-west-2
export AWS_DEFAULT_REGION=us-west-2
python3 infra/layer-manager/scripts/preflight_identity.py \
  --profile mfeng --region us-west-2
python3 infra/layer-manager/scripts/preflight_identity.py \
  --profile mfeng --region us-west-2 --call-sts
```

The first command does not call AWS. `--call-sts` must show account `544020760996`. Stop if it does not.

## Package

From the repository root:

```bash
python3 infra/layer-manager/scripts/package_lambda.py \
  --out infra/layer-manager/dist/layer-manager-lambda.zip
python3 infra/layer-manager/scripts/package_site.py \
  --out infra/layer-manager/dist/site
```

The site directory has no `config.js` and no fixture catalog.

## Artifact bucket

```bash
aws cloudformation deploy \
  --profile mfeng \
  --region us-west-2 \
  --stack-name geo-map-layer-manager-staging-artifacts \
  --template-file infra/layer-manager/bootstrap-artifact-bucket.yaml \
  --no-execute-changeset
```

Read the changeset. It creates only `geo-map-layer-manager-staging-artifacts-544020760996`. Then run the same command without `--no-execute-changeset`.

```bash
aws s3 cp --profile mfeng --region us-west-2 \
  infra/layer-manager/dist/layer-manager-lambda.zip \
  s3://geo-map-layer-manager-staging-artifacts-544020760996/lambda/layer-manager-lambda.zip
```

Refuse the copy if the destination contains `geo-map-tiles`.

## Registry stack

Pick a Cognito domain prefix that is free in Amazon Cognito. A suggested value is `tp-geomap-layers-544020760996`. Leave `TileBackendBaseUrl` empty until the performance-branch test endpoint exists.

```bash
aws cloudformation deploy \
  --profile mfeng \
  --region us-west-2 \
  --stack-name geo-map-layer-manager-staging \
  --template-file infra/layer-manager/template.yaml \
  --parameter-overrides \
    ArtifactKey=lambda/layer-manager-lambda.zip \
    CognitoDomainPrefix=tp-geomap-layers-544020760996 \
    TileBackendBaseUrl= \
    TilePathOrder=map \
  --no-execute-changeset
```

Check the changeset for these absences: Route 53, `admin.terrapulse.com`, `geo-map-tiles`, a public bucket, an unauthenticated `/v1` route, and a Cognito user. Then deploy without `--no-execute-changeset`.

Useful outputs: `ConsoleUrl`, `DistributionDomainName`, `DistributionId`, `HttpApiEndpoint`, `FrontendBucketName`, `RegistryTableName`, `UserPoolId`, `UserPoolClientId`, `HostedUiBaseUrl`, `ApiRoleArn`, `SeedInserted`, `TileBackendBaseUrl`, `TilePathOrder`.

`SeedInserted` should be `3` on the first create. Those rows are synthetic fixtures. The seed does not overwrite a later edit.

## Console files

```bash
aws cloudformation describe-stacks \
  --profile mfeng --region us-west-2 \
  --stack-name geo-map-layer-manager-staging \
  --query "Stacks[0].Outputs" --output json > /tmp/layer-manager-outputs.json
python3 - << 'PY'
import json
raw = json.load(open("/tmp/layer-manager-outputs.json"))
flat = {item["OutputKey"]: item["OutputValue"] for item in raw}
json.dump(flat, open("/tmp/layer-manager-outputs-flat.json", "w"))
PY
python3 infra/layer-manager/scripts/render_config.py \
  --outputs /tmp/layer-manager-outputs-flat.json \
  --out infra/layer-manager/dist/site/config.js
aws s3 sync --profile mfeng --region us-west-2 \
  infra/layer-manager/dist/site \
  "s3://$(python3 -c 'import json; print(json.load(open("/tmp/layer-manager-outputs-flat.json"))["FrontendBucketName"])')/"
aws cloudfront create-invalidation --profile mfeng \
  --distribution-id "$(python3 -c 'import json; print(json.load(open("/tmp/layer-manager-outputs-flat.json"))["DistributionId"])')" \
  --paths "/*"
```

Use the frontend bucket name from the stack output only.

## Wiring the performance-branch test API later

When that isolated endpoint exists, update the stack with `TileBackendBaseUrl=https://...` and the matching `TilePathOrder`. Re-render `config.js` and sync the site. Do not add that origin to the admin API CORS list. The console will show addresses and will not call the tile API. See `management/docs/tile-backend-preview-contract.md`.

## Rollback and delete

A failed create or update rolls back automatically. `aws cloudformation cancel-update-stack` stops an update that is still running.

A bad registry edit is restored through `POST /v1/layers/item/restore` with confirmation `restore-registry-only`. That writes a new revision. It does not delete the audit row and does not regenerate PNGs.

Static files can be restored from the frontend bucket's noncurrent versions for 30 days. Lambda code is the zip key in the artifact bucket; redeploy the previous key.

Delete the application stack before the artifact stack. Empty only the buckets named by the stack outputs:

```bash
aws s3 rm --profile mfeng --region us-west-2 \
  "s3://FRONTEND_BUCKET_FROM_OUTPUT" --recursive
aws cloudformation delete-stack --profile mfeng --region us-west-2 \
  --stack-name geo-map-layer-manager-staging
aws cloudformation wait stack-delete-complete --profile mfeng --region us-west-2 \
  --stack-name geo-map-layer-manager-staging
aws s3 rm --profile mfeng --region us-west-2 \
  "s3://geo-map-layer-manager-staging-artifacts-544020760996" --recursive
aws cloudformation delete-stack --profile mfeng --region us-west-2 \
  --stack-name geo-map-layer-manager-staging-artifacts
```

Deletion removes the staging table, the empty user pool, the new buckets, the distribution, the API, and the function. It does not remove production tile objects or DNS.

## Idle cost

There is no NAT gateway, load balancer, or database server. Idle cost is usually under a few dollars a month:

- Lambda and HTTP API are billed on use. Reserved concurrency is 2, which can reserve a small slice of account concurrency but does not add a per-hour fee the way provisioned concurrency does.
- DynamoDB is on-demand. Point-in-time recovery is on by default and is the main registry storage cost; set `EnablePitr=false` to drop it.
- Cognito stays in the free tier at this size. MFA is a software token. Advanced security is not enabled. No invitation email is sent because no user is created.
- CloudFront is price class 100. The private bucket is tiny. Noncurrent console versions expire after 30 days.
- Log groups retain 14 days. API access logs omit the authorization header and JWT claims. The stage throttles at 10 requests per second, burst 20.

## First admin, later

```bash
aws cognito-idp admin-create-user \
  --profile mfeng --region us-west-2 \
  --user-pool-id USER_POOL_ID_FROM_OUTPUT \
  --username CONFIRMED_EMAIL \
  --message-action SUPPRESS
aws cognito-idp admin-add-user-to-group \
  --profile mfeng --region us-west-2 \
  --user-pool-id USER_POOL_ID_FROM_OUTPUT \
  --username CONFIRMED_EMAIL \
  --group-name layer-admin
```

`SUPPRESS` avoids an unsolicited invitation. Deliver the temporary password out of band. The hosted UI then requires a new password and a TOTP factor because MFA is required. Do not run this until the owner's identity is confirmed.
