#!/usr/bin/env python3
"""Load the JSON library and execute requests without network access."""

import argparse
import ctypes
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()

    library = ctypes.CDLL(str(args.library.resolve()))
    execute = library.td_json_client_execute
    execute.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    execute.restype = ctypes.c_char_p

    for name, expected in (("version", args.version), ("commit_hash", args.commit)):
        request = json.dumps({"@type": "getOption", "name": name}).encode()
        raw = execute(None, request)
        if raw is None:
            raise RuntimeError(f"getOption({name}) returned no response")
        response = json.loads(raw)
        if response.get("@type") != "optionValueString" or response.get("value") != expected:
            raise RuntimeError(f"Expected {name}={expected!r}, got {response!r}")
        print(f"Verified {name}: {expected}")

    # Also check that generated JSON request/response code works.
    raw = execute(None, b'{"@type":"getTextEntities","text":"https://telegram.org"}')
    response = json.loads(raw) if raw else None
    if not response or response.get("@type") != "textEntities" or not response.get("entities"):
        raise RuntimeError(f"getTextEntities failed: {response!r}")
    print(f"Verified JSON API: {args.library}")


if __name__ == "__main__":
    main()
