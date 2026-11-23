"""Start the local registry UI.

This process is for development and screenshots. It refuses to start unless
LAYER_MANAGER_ENV is local, and it never calls AWS.
"""

import argparse
import os
import sys

from .app_factory import build_api
from .local_server import make_server, prepare_local
from .settings import Settings


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local geo-map layer registry. Does not deploy.")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    os.environ.setdefault("LAYER_MANAGER_ENV", "local")
    os.environ.setdefault("LAYER_MANAGER_AUTH_MODE", "local-fixture")
    os.environ.setdefault("LAYER_MANAGER_ALLOW_FIXTURE_AUTH", "1")
    os.environ.setdefault("LAYER_MANAGER_SEED_FIXTURES", "1")
    os.environ.setdefault("LAYER_MANAGER_REPOSITORY", "file")
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".data"))
    os.environ.setdefault("LAYER_MANAGER_FILE_ROOT", root)
    os.environ.setdefault("LAYER_MANAGER_CORS_ORIGINS", f"http://127.0.0.1:{args.port}")
    os.environ.setdefault("LAYER_MANAGER_EMIT_CORS", "1")
    settings = Settings.from_env()
    if settings.env != "local":
        print("Refusing to start. The local server only runs when LAYER_MANAGER_ENV=local.", file=sys.stderr)
        return 2
    api = prepare_local(settings, build_api(settings))
    server = make_server(settings, api, args.port)
    print("geo-map layer manager local UI")
    print("Synthetic fixtures only. This is not the live tile inventory.")
    print("No AWS calls. PNG pyramids are not regenerated.")
    print(f"http://127.0.0.1:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
