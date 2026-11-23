"""Per-dataset read checks shared by HTTP, WMS, and MCP."""

from dataclasses import dataclass

from .registry import Access


@dataclass(frozen=True)
class Principal:
    subject: str
    roles: frozenset[str]
    anonymous: bool = False


ANONYMOUS = Principal(subject="anonymous", roles=frozenset(), anonymous=True)


def can_read(access: Access, principal: Principal) -> bool:
    if access.visibility == "public":
        return True
    if principal.anonymous:
        return False
    return bool(set(access.read_roles) & set(principal.roles))
