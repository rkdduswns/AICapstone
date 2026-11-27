"""Chrome Native Messaging host: return the current ContextTrace local token."""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path


def _read_message() -> dict | None:
    raw_length = sys.stdin.buffer.read(4)
    if not raw_length:
        return None
    if len(raw_length) != 4:
        raise ValueError("Incomplete native message header")
    message_length = struct.unpack("<I", raw_length)[0]
    if message_length > 1024 * 1024:
        raise ValueError("Native message is too large")
    raw_message = sys.stdin.buffer.read(message_length)
    if len(raw_message) != message_length:
        raise ValueError("Incomplete native message body")
    value = json.loads(raw_message.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Native message must be an object")
    return value


def _write_message(value: dict) -> None:
    encoded = json.dumps(value, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def main() -> int:
    try:
        request = _read_message()
        if request is None:
            return 0
        if request.get("type") != "get_token":
            _write_message({"ok": False, "error": "unsupported_request"})
            return 0

        token_path = Path.home() / ".contexttrace" / "browser-token"
        token = token_path.read_text(encoding="utf-8").strip()
        if len(token) < 64:
            raise ValueError("Browser token is missing or invalid")
        _write_message({"ok": True, "token": token})
    except Exception:
        # Never print token data or exception details to stdout/stderr.
        _write_message({"ok": False, "error": "authentication_unavailable"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
