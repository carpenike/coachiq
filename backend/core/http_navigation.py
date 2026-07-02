"""HTTP navigation helpers shared by middleware and route fallback code."""

from typing import Any


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
