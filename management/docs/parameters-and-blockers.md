# Parameters and blockers

Target, when the parent deploys: account `544020760996`, region `us-west-2`, CLI profile `tp`. The profile name is not the IAM user name. This implementation did not call AWS and did not deploy.

## Required before the stack can be created

| Parameter | Why it blocks |
| --- | --- |
| `ArtifactKey` | No default. The Lambda zip must already be in the new artifact bucket. |
| `CognitoDomainPrefix` | No default. The prefix is global. Suggested `tp-geomap-layers-544020760996`. If it is taken, choose another. |
| Account and region rules | The template asserts account `544020760996` and region `us-west-2`. |

## Supplied by the parent later

| Item | State in this branch |
| --- | --- |
| Tile test endpoint | `TileBackendBaseUrl` default is empty. Preview status is `awaiting-parent-endpoint`. Not integrated. |
| First admin | Pool has no users and sends no invitations. Enroll with `--message-action SUPPRESS` after the identity is confirmed. MFA is required. |
| Registry schema in `interfaces/` | Not copied. Parent reconciles `layer-registry-v1.schema.json` before shared use. |
| Production catalog | Refused. Fixtures are synthetic. Live `setting.ini` paths that name `geo-map-tiles` cannot be stored. |

## Safe to leave at defaults

`Stage=staging`, `SeedSyntheticFixtures=true`, `TilePathOrder=map`, `PreviewAllowedHosts` empty, `EnablePitr=true`, `ReservedConcurrentExecutions=2`.

`ReservedConcurrentExecutions` fails if the account cannot reserve that many executions. Lower the parameter; do not set it to 0, because zero reserved concurrency stops every invoke.
