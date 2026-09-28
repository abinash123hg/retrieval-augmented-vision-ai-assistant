"""Input safety: file type checks, filename sanitization, path containment."""

import re
from pathlib import Path

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}

# Minimal magic-byte signatures for the allowed types.
_MAGIC = {
    ".pdf": [b"%PDF"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
}

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def is_allowed_extension(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def matches_magic_bytes(extension: str, head: bytes) -> bool:
    signatures = _MAGIC.get(extension.lower())
    if not signatures:
        return False
    return any(head.startswith(sig) for sig in signatures)


def sanitize_filename(filename: str) -> str:
    name = Path(filename).name
    name = _SAFE_NAME.sub("_", name).strip("._")
    return name or "unnamed"


def is_within_directory(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False
