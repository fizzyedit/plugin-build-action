#!/usr/bin/env python3
"""dlopen a built Fizzy plugin and read the C-ABI identity / SDK exports.

Prints JSON on stdout:
  {
    "id": "...",
    "version": "X.Y.Z",
    "abi_fingerprint": "0x...",
    "fizzy_sdk_version": "X.Y.Z",
    "min_sdk_version": "X.Y.Z"
  }

`fizzy_sdk_version` and `abi_fingerprint` come from the pinned fizzy commit the
plugin was built against (embedded at compile time) — callers must not hand-copy
them into workflow YAML. Stdlib + ctypes only.
"""
from __future__ import annotations

import ctypes
import json
import sys
from pathlib import Path


class VersionTriplet(ctypes.Structure):
    _fields_ = (
        ("major", ctypes.c_uint32),
        ("minor", ctypes.c_uint32),
        ("patch", ctypes.c_uint32),
    )


def _triplet(lib: ctypes.CDLL, name: str) -> str:
    fn = getattr(lib, name)
    fn.restype = VersionTriplet
    fn.argtypes = []
    t = fn()
    return f"{t.major}.{t.minor}.{t.patch}"


def _cstr(lib: ctypes.CDLL, name: str) -> str:
    fn = getattr(lib, name)
    fn.restype = ctypes.c_char_p
    fn.argtypes = []
    raw = fn()
    if raw is None:
        raise RuntimeError(f"{name} returned null")
    return raw.decode("utf-8")


def main() -> int:
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} <plugin.dylib|so|dll>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"::error::plugin binary not found: {path}", file=sys.stderr)
        return 1

    loader = ctypes.WinDLL if sys.platform.startswith("win") else ctypes.CDLL
    try:
        lib = loader(str(path.resolve()))
    except OSError as e:
        print(f"::error::dlopen failed for {path}: {e}", file=sys.stderr)
        return 1

    fp_fn = lib.fizzy_plugin_abi_fingerprint
    fp_fn.restype = ctypes.c_uint64
    fp_fn.argtypes = []
    fingerprint = fp_fn()

    try:
        out = {
            "id": _cstr(lib, "fizzy_plugin_id"),
            "version": _triplet(lib, "fizzy_plugin_version"),
            "abi_fingerprint": f"0x{fingerprint:x}",
            "fizzy_sdk_version": _triplet(lib, "fizzy_plugin_sdk_version"),
            "min_sdk_version": _triplet(lib, "fizzy_plugin_min_sdk_version"),
        }
    except Exception as e:  # noqa: BLE001
        print(f"::error::failed reading exports from {path}: {e}", file=sys.stderr)
        return 1

    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
