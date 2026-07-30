#!/usr/bin/env python3
"""Read identity fields from a Fizzy plugin's root `plugin.zig.zon`.

Prints a single JSON object on stdout:
  { "id", "name", "version", "min_sdk_version", "description", "tags", "author", "author_url" }

`min_sdk_version` may be "" (empty) — the build defaults it to the pinned fizzy
`sdk_version` at compile time. `description`/`tags` may be "" / [] — both are optional fields
on the author's `plugin.zig.zon` (see fizzy's `src/sdk/manifest.zig`). Stdlib only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _field(text: str, key: str) -> str | None:
    # Match `.key = "value"` or `.key = ""`, ignoring // line comments roughly by
    # scanning line-by-line.
    pat = re.compile(
        rf'^\s*\.{re.escape(key)}\s*=\s*"([^"]*)"\s*,?\s*(?://.*)?$',
        re.MULTILINE,
    )
    m = pat.search(text)
    return m.group(1) if m else None


def _array_field(text: str, key: str) -> list[str]:
    # Match `.key = .{ "a", "b", ... }`, possibly spanning multiple lines — good enough for the
    # plain string-literal arrays plugin.zig.zon actually declares (no nested structs/exprs).
    pat = re.compile(rf'\.{re.escape(key)}\s*=\s*\.\{{(.*?)\}}', re.DOTALL)
    m = pat.search(text)
    if not m:
        return []
    return re.findall(r'"([^"]*)"', m.group(1))


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "plugin.zig.zon")
    if not path.is_file():
        print(f"::error::missing {path} — every plugin needs a root plugin.zig.zon", file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8")
    # Strip block comments naively (zon files here are simple).
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

    plugin_id = _field(text, "id")
    version = _field(text, "version")
    if not plugin_id or not version:
        print(f"::error::{path} must declare .id and .version strings", file=sys.stderr)
        return 1

    out = {
        "id": plugin_id,
        "name": _field(text, "name") or plugin_id,
        "version": version,
        "min_sdk_version": _field(text, "min_sdk_version") or "",
        "description": _field(text, "description") or "",
        "tags": _array_field(text, "tags"),
        "author": _field(text, "author") or "",
        "author_url": _field(text, "author_url") or "",
    }
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
