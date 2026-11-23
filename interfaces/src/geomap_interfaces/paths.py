"""Reject paths that leave a configured root. No network lookups."""

from pathlib import Path

from .errors import InterfaceError

_SEGMENT = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-")


def dataset_id_error(value: str) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 240:
        return "dataset id length is invalid"
    parts = value.split("/")
    if len(parts) > 8:
        return "dataset id has too many segments"
    for part in parts:
        if not part or part in {".", ".."}:
            return "dataset id segment is empty or relative"
        if part[0] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789":
            return "dataset id segment must start with a letter or digit"
        if any(ch not in _SEGMENT for ch in part):
            return "dataset id segment has a disallowed character"
    return None


def require_dataset_id(value: str) -> str:
    error = dataset_id_error(value)
    if error:
        raise InterfaceError("not_found", "unknown dataset", 404)
    return value


def safe_join(root: Path, relative: str) -> Path:
    """Resolve ``relative`` and require the result to stay inside ``root``."""

    base = root.resolve()
    if not isinstance(relative, str) or not relative or relative.startswith(("/", "\\")) or "\\" in relative:
        raise InterfaceError("invalid_path", "path escapes the data root", 400)
    parts = Path(relative).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise InterfaceError("invalid_path", "path escapes the data root", 400)
    resolved = base.joinpath(*parts).resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise InterfaceError("invalid_path", "path escapes the data root", 400) from exc
    return resolved
