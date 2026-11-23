#!/bin/bash
# Parent AWS executor only. The coding agent must not run this script.
# Account 544020760996, region us-west-2. Isolated stack. Does not merge and
# does not change production /maptiles.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ZIP="${ZIP:-$ROOT/build/geomap-tile-pyramid-test-py312-x86_64.zip}"
ARTIFACT_BUCKET="${ARTIFACT_BUCKET:?set ARTIFACT_BUCKET to a deploy-artifact bucket you already own}"
ARTIFACT_KEY="${ARTIFACT_KEY:-geomap-tile-pyramid-test/geomap-tile-pyramid-test-py312-x86_64.zip}"
AUTH_MODE="${AUTH_MODE:-iam}"
TILE_BUCKET="${TILE_BUCKET:-}"
TILE_KEY_PREFIX="${TILE_KEY_PREFIX:-tile-pyramid-test/}"
CORS_ORIGIN="${CORS_ORIGIN:-}"
TILE_AUTH_TOKEN="${TILE_AUTH_TOKEN:-}"

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"
test "$ACCOUNT" = "544020760996"
test "$REGION" = "us-west-2"
test -f "$ZIP"

aws s3 cp "$ZIP" "s3://${ARTIFACT_BUCKET}/${ARTIFACT_KEY}" --region "$REGION"

OVERRIDES=(
  "ArtifactBucket=${ARTIFACT_BUCKET}"
  "ArtifactKey=${ARTIFACT_KEY}"
  "AuthMode=${AUTH_MODE}"
  "TileBucket=${TILE_BUCKET}"
  "TileKeyPrefix=${TILE_KEY_PREFIX}"
  "CorsOrigin=${CORS_ORIGIN}"
)
if [[ "$AUTH_MODE" == "header" ]]; then
  if [[ -z "$TILE_AUTH_TOKEN" ]]; then
    echo "AuthMode header requires TILE_AUTH_TOKEN in the environment, not in git" >&2
    exit 1
  fi
  OVERRIDES+=("TileAuthToken=${TILE_AUTH_TOKEN}")
fi

aws cloudformation deploy \
  --region "$REGION" \
  --stack-name geomap-tile-pyramid-test \
  --template-file "$ROOT/infra/tile_pyramid_test/template.yaml" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides "${OVERRIDES[@]}"

aws cloudformation describe-stacks \
  --region "$REGION" \
  --stack-name geomap-tile-pyramid-test \
  --query 'Stacks[0].Outputs' \
  --output table
