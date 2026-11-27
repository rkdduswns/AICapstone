"""Create and persist a local credential shared with the Chrome native host."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


def browser_token_path() -> Path:
    """Return the per-user browser credential path."""
    return Path.home() / ".contexttrace" / "browser-token"


def load_or_create_browser_token(path: str | Path | None = None) -> str:
    """Load the local token or create it once without overwriting an existing one."""
    token_path = Path(path) if path is not None else browser_token_path()
    token_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        token = token_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        token = ""

    if token:
        if len(token) < 64:
            raise RuntimeError("Stored browser token is invalid; remove it to regenerate")
        return token

    generated = secrets.token_urlsafe(48)
    try:
        descriptor = os.open(
            token_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        token = token_path.read_text(encoding="utf-8").strip()
        if len(token) < 64:
            raise RuntimeError("Stored browser token is invalid")
        return token

    with os.fdopen(descriptor, "w", encoding="utf-8") as token_file:
        token_file.write(generated)
        token_file.write("\n")

    try:
        token_path.chmod(0o600)
    except OSError:
        # Windows permissions are inherited from the user's profile directory.
        pass

    return generated
