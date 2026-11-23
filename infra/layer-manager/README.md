# Staging infrastructure

Two templates, both limited to account `544020760996` and `us-west-2`:

- `bootstrap-artifact-bucket.yaml` creates `geo-map-layer-manager-staging-artifacts-544020760996`.
- `template.yaml` creates the private console bucket, CloudFront default domain, HTTP API, Lambda, DynamoDB registry, and an empty Cognito pool.

Neither template names `admin.terrapulse.com`, a production tile bucket, or a Route 53 record. `TileBackendBaseUrl` defaults to empty. The performance-branch test API is supplied later by the parent and is not called by this stack.

Deploy, rollback, and the first-admin procedure are in `management/docs/operations.md`. The preview address contract is in `management/docs/tile-backend-preview-contract.md`.

```bash
python3 -m unittest discover -s infra/layer-manager/tests -v
```

Run that from the repository root after installing PyYAML. The test does not call AWS.
