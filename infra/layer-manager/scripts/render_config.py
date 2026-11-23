#!/usr/bin/env python3
"""Render public config.js from stack outputs. Does not call AWS."""

import argparse
import json
from pathlib import Path

FORBIDDEN_KEYS = ("secret", "password", "accesskey", "sessiontoken")
FORBIDDEN_TEXT = ("admin.terrapulse.com", "geo-map-tiles", "map-tiles-dev", "*")


def render(outputs: dict) -> str:
    blob = json.dumps(outputs).lower()
    for key in outputs:
        if any(word in key.lower() for word in FORBIDDEN_KEYS):
            raise SystemExit(f"Refusing output key {key}. config.js cannot carry secrets.")
    for text in FORBIDDEN_TEXT:
        if text in blob:
            raise SystemExit(f"Refusing to render config.js because it contains {text}.")
    required = ("HttpApiEndpoint", "UserPoolClientId", "HostedUiBaseUrl", "DistributionDomainName")
    missing = [key for key in required if not outputs.get(key)]
    if missing:
        raise SystemExit("Missing stack outputs: " + ", ".join(missing))
    config = {
        "authMode": "apigateway-cognito",
        "environment": "staging",
        "apiBase": str(outputs["HttpApiEndpoint"]).rstrip("/"),
        "syntheticFixtures": True,
        "signup": False,
        "cognito": {
            "hostedUiBase": str(outputs["HostedUiBaseUrl"]).rstrip("/"),
            "clientId": outputs["UserPoolClientId"],
            "redirectUri": f"https://{outputs['DistributionDomainName']}/",
        },
        "effectsNotice": "Saving or publishing changes the registry only. Existing PNG pyramids are not regenerated.",
        "tileBackend": {
            "baseUrl": (str(outputs.get("TileBackendBaseUrl") or "").rstrip("/") or None),
            "pathOrder": outputs.get("TilePathOrder") or "map",
            "integrated": False,
            "callsBackend": False,
            "publishGeneratesTiles": False,
        },
    }
    return "window.LAYER_MANAGER_CONFIG = " + json.dumps(config, indent=2) + ";\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Render config.js from a JSON object of stack outputs.")
    parser.add_argument("--outputs", required=True, help="JSON file of stack outputs. No network.")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    outputs = json.loads(Path(args.outputs).read_text(encoding="utf-8"))
    Path(args.out).write_text(render(outputs), encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
