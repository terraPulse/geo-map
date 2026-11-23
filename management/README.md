# geo-map layer registry

Staging admin console for layer metadata. It does not serve tiles, does not regenerate PNG pyramids, and does not write `setting.ini`.

The legacy tile service stays on `serv/` and `util/`. Pull request 2 (`cursor/tile-view-correctness-720a`) is the performance-branch renderer. This app can display a preview address for that renderer once the parent supplies a test base URL. Until then the address is absent and `integrated` is false.

```bash
cd management
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --test tests/ui_auth.test.js
PYTHONPATH=src python3 -m layer_manager --port 8765
```

The local server loads synthetic fixtures and accepts only the `fixture-admin` and `fixture-reader` identities. It does not call AWS.

Contracts and operations:

- `docs/tile-backend-preview-contract.md`
- `docs/dataset-schema-contract.md`
- `docs/architecture.md`
- `docs/operations.md`
- `docs/parameters-and-blockers.md`
- `docs/security-review.md`
- `contracts/layer-registry-v1.schema.json`

Infrastructure lives in `infra/layer-manager/`. This tree does not modify `interfaces/`.
