"""Run with python -m backend [--port 8765]."""

import argparse

import uvicorn

from shared.protocol import DEFAULT_PORT


def port_number(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer from 1 to 65535") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be an integer from 1 to 65535")
    return port


def main() -> None:
    parser = argparse.ArgumentParser(description="ContextTrace local backend")
    parser.add_argument("--port", type=port_number, default=DEFAULT_PORT)
    args = parser.parse_args()
    # Uvicorn logs startup/shutdown and exits nonzero on a bind failure.
    uvicorn.run("backend.app:app", host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
