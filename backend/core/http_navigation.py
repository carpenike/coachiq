"""HTTP navigation helpers shared by middleware and route fallback code."""

import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote

_HASHED_SPA_JAVASCRIPT_PATH = re.compile(
    r"^/assets/[A-Za-z0-9][A-Za-z0-9._-]*-[A-Za-z0-9_-]{8,}\.js$"
)


def accepts_html(request: Any) -> bool:
    """Return whether a request accepts an HTML document response."""
    accept_header = getattr(request, "headers", {}).get("accept", "")
    accepted_types = [
        part.split(";", maxsplit=1)[0].strip().lower() for part in accept_header.split(",")
    ]
    return "text/html" in accepted_types


def route_family(path: str) -> str | None:
    """Return the root-mounted route family for a path."""
    if not path or path == "/":
        return None
    return f"/{path.lstrip('/').split('/', maxsplit=1)[0]}"


def is_hashed_spa_javascript_path(request_path: str) -> bool:
    """Return whether a path looks like a Vite-generated JavaScript asset."""
    return _HASHED_SPA_JAVASCRIPT_PATH.fullmatch(unquote(request_path)) is not None


def safe_spa_file_path(spa_dir: str | Path, request_path: str) -> Path | None:
    """Resolve an existing SPA file without allowing directory escape."""
    relative_path = unquote(request_path).lstrip("/")
    if not relative_path:
        return None

    root = Path(spa_dir).resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None

    return candidate if candidate.is_file() else None
