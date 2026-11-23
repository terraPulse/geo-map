"""Authentication.

Staging trusts claims only after API Gateway's Cognito JWT authorizer has
verified the signature. This module re-checks issuer, audience, expiry,
token use, and group. Anonymous requests are denied.

Local fixture actors exist only when settings explicitly allow them. They
are synthetic identities and are never accepted in staging.
"""

import json
import time

from .errors import Forbidden, Unauthorized
from .schema_contract import ROLE_ADMIN, ROLE_READER

_GROUP_NAMES = {ROLE_ADMIN, ROLE_READER}


class Actor:
    def __init__(self, sub, username, role, synthetic_identity, auth_mode):
        self.sub = sub
        self.username = username
        self.role = role
        self.synthetic_identity = synthetic_identity
        self.auth_mode = auth_mode

    def to_dict(self):
        return {
            "sub": self.sub,
            "username": self.username,
            "role": self.role,
            "synthetic_identity": self.synthetic_identity,
            "auth_mode": self.auth_mode,
        }


def _groups(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if not isinstance(value, str):
        return []
    text = value.strip()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            inner = text.strip("[]")
            parts = [part.strip().strip('"').strip("'") for part in inner.replace(",", " ").split()]
            return [part for part in parts if part]
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    if " " in text or "," in text:
        return [part.strip() for part in text.replace(",", " ").split() if part.strip()]
    return [text]


def _role_from_groups(groups):
    found = [group for group in groups if group in _GROUP_NAMES]
    if ROLE_ADMIN in found:
        return ROLE_ADMIN
    if ROLE_READER in found:
        return ROLE_READER
    return None


def _issuer(region, user_pool_id):
    return f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"


def actor_from_apigateway_event(event, settings, now=None):
    """Read an API Gateway HTTP API v2 or REST authorizer context."""
    context = (event or {}).get("requestContext") or {}
    authorizer = context.get("authorizer") or {}
    jwt = authorizer.get("jwt") or {}
    claims = jwt.get("claims") or authorizer.get("claims") or {}
    if not isinstance(claims, dict) or not claims:
        raise Unauthorized("Anonymous access is denied. A Cognito JWT authorizer context is required.")
    return actor_from_claims(claims, settings, now=now)


def actor_from_claims(claims, settings, now=None):
    if settings.auth_mode != "apigateway-cognito":
        raise Unauthorized("Cognito claims are not accepted in this auth mode.")
    if not settings.cognito_region or not settings.cognito_user_pool_id or not settings.cognito_client_id:
        raise Unauthorized("Cognito issuer is not configured. Refusing the request.")
    issuer = claims.get("iss")
    expected = _issuer(settings.cognito_region, settings.cognito_user_pool_id)
    if issuer != expected:
        raise Unauthorized("Token issuer does not match the staging user pool.")
    audience = claims.get("aud") or claims.get("client_id")
    if audience != settings.cognito_client_id:
        raise Unauthorized("Token audience does not match the staging app client.")
    if claims.get("token_use") not in {"access", "id"}:
        raise Unauthorized("Token use must be access or id.")
    exp = claims.get("exp")
    try:
        exp_value = int(exp)
    except (TypeError, ValueError) as exc:
        raise Unauthorized("Token expiry is missing.") from exc
    current = int(time.time() if now is None else now)
    if exp_value <= current:
        raise Unauthorized("Token is expired.")
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise Unauthorized("Token subject is missing.")
    role = _role_from_groups(_groups(claims.get("cognito:groups")))
    if role is None:
        raise Forbidden("The signed-in user is not in layer-admin or layer-reader. No open signup is available.")
    username = claims.get("username") or claims.get("cognito:username") or claims.get("email") or sub
    return Actor(sub, str(username), role, False, "apigateway-cognito")


def actor_from_fixture_header(headers, settings):
    if not settings.allow_fixture_auth or settings.auth_mode != "local-fixture" or settings.env not in {"local", "test"}:
        return None
    wanted = None
    for key, value in (headers or {}).items():
        if key.lower() == "x-layer-manager-fixture-actor":
            wanted = value.strip()
    if not wanted:
        return None
    if wanted == "fixture-admin":
        return Actor("fixture-admin", "fixture-admin", ROLE_ADMIN, True, "local-fixture")
    if wanted == "fixture-reader":
        return Actor("fixture-reader", "fixture-reader", ROLE_READER, True, "local-fixture")
    raise Unauthorized("Unknown local fixture actor. There is no signup.")


def authenticate(event_headers, apigateway_event, settings, now=None):
    if settings.auth_mode == "local-fixture":
        actor = actor_from_fixture_header(event_headers, settings)
        if actor is None:
            raise Unauthorized("Anonymous access is denied. Continue with a local fixture identity.")
        return actor
    if settings.auth_mode == "apigateway-cognito":
        # Fixture headers must not become a backdoor when the API is staged.
        return actor_from_apigateway_event(apigateway_event, settings, now=now)
    raise Unauthorized("Auth mode is not configured. Anonymous access is denied.")


def require_writer(actor):
    if actor.role != ROLE_ADMIN:
        raise Forbidden("This action requires the layer-admin role.")
