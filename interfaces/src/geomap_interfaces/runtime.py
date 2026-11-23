"""Process configuration. Tokens come from the caller or the environment, never the registry."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .auth import Principal
from .budgets import Budgets
from .errors import InterfaceError, RegistryError
from .pyramid import BlockStore
from .registry import Registry, load_registry


@dataclass
class Runtime:
    registry: Registry
    data_root: Path
    public_base: str
    budgets: Budgets
    tokens: dict[str, Principal] = field(default_factory=dict)
    store: BlockStore | None = None

    def __post_init__(self) -> None:
        self.data_root = Path(self.data_root).resolve()
        self.public_base = self.public_base.rstrip("/")
        if self.store is None:
            self.store = BlockStore(self.data_root)


def load_runtime(config_path: Path, tokens: dict[str, Principal] | None = None) -> Runtime:
    path = Path(config_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RegistryError("runtime config must be an object")
    allowed = {"registry", "data_root", "public_base", "budgets"}
    extra = sorted(set(payload) - allowed)
    if extra:
        raise RegistryError("runtime config has unknown fields: " + ", ".join(extra))
    budgets = _budgets(payload.get("budgets") or {})
    registry_path = path.parent / payload["registry"]
    data_root = path.parent / payload["data_root"]
    return Runtime(
        registry=load_registry(registry_path, budgets),
        data_root=data_root,
        public_base=str(payload.get("public_base") or ""),
        budgets=budgets,
        tokens=tokens if tokens is not None else tokens_from_env(),
    )


def tokens_from_env(name: str = "GEOMAP_INTERFACE_TOKENS") -> dict[str, Principal]:
    raw = os.environ.get(name)
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InterfaceError("invalid_request", "token environment is not valid JSON", 500) from exc
    if not isinstance(payload, dict):
        raise InterfaceError("invalid_request", "token environment must be an object", 500)
    tokens: dict[str, Principal] = {}
    for token, record in payload.items():
        if not isinstance(token, str) or not token or not isinstance(record, dict):
            raise InterfaceError("invalid_request", "token environment has an invalid entry", 500)
        roles = record.get("roles", [])
        subject = record.get("subject")
        if not isinstance(subject, str) or not subject or not isinstance(roles, list):
            raise InterfaceError("invalid_request", "token environment has an invalid entry", 500)
        tokens[token] = Principal(subject=subject, roles=frozenset(str(role) for role in roles), anonymous=False)
    return tokens


def _budgets(payload: dict) -> Budgets:
    if not isinstance(payload, dict):
        raise RegistryError("budgets must be an object")
    known = {item.name for item in Budgets.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    extra = sorted(set(payload) - known)
    if extra:
        raise RegistryError("budgets has unknown fields: " + ", ".join(extra))
    budgets = Budgets(**payload)
    budgets.check()
    return budgets
