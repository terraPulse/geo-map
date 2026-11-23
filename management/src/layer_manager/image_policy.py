"""Worker image names the stack will accept. A request cannot substitute another image."""

import re

from .errors import ConfigurationError

IMAGE_RE = re.compile(
    r"^544020760996\.dkr\.ecr\.us-west-2\.amazonaws\.com/geo-map-layer-manager-worker:"
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
)


def validate_image_uri(uri):
    if not isinstance(uri, str) or not IMAGE_RE.match(uri) or uri.endswith(":latest"):
        raise ConfigurationError(
            "Worker image must be 544020760996.dkr.ecr.us-west-2.amazonaws.com/"
            "geo-map-layer-manager-worker:<tag>, and the tag cannot be latest."
        )
    return uri
