#!/usr/bin/env python3
"""Edit a Fizzy plugin's pins for `repin.yml`. Stdlib only.

  repin_zon.py current build.zig.zon
      Prints the fizzy SDK version the `.fizzy` dependency pins (from its release-asset URL).
      Exits 2 when the dependency is a `.path` or a URL that is not an `sdk-v*` release asset.

  repin_zon.py pin build.zig.zon <url> <hash>
      Points the `.fizzy` dependency at <url> with <hash>, leaving the rest of the file alone.

  repin_zon.py bump plugin.zig.zon <sdk-version> [<released-version>]
      Sets `.min_sdk_version` to <sdk-version> and prints the version the repin releases as:
      `.version` with its patch bumped, unless it is already past <released-version> (a bump
      already on the branch, not yet released), which is kept.

  repin_zon.py released manifest.json
      Prints the newest release the plugin's published manifest lists, as `<version>
      <abi_fingerprint>`: what the store hands out now.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SDK_URL = re.compile(r"/sdk-v(\d+\.\d+\.\d+)/fizzy-sdk-v\1\.tar\.gz")


def _fizzy_block(text: str) -> re.Match[str]:
    # The dependency's struct: `.fizzy = .{` up to the `},` closing it. Its fields are plain
    # strings and comments, so the first `},` on a line of its own ends it.
    m = re.search(r"\.fizzy\s*=\s*\.\{(.*?)\n\s*\},", text, re.DOTALL)
    if not m:
        sys.exit("no `.fizzy = .{ ... }` dependency in build.zig.zon")
    return m


def current(zon: Path) -> int:
    block = _fizzy_block(zon.read_text()).group(1)
    url = re.search(r'\.url\s*=\s*"([^"]*)"', block)
    if not url:
        print("the fizzy dependency is not pinned by URL (a `.path`?): repin works on a release pin", file=sys.stderr)
        return 2
    version = SDK_URL.search(url.group(1))
    if not version:
        print(f"the fizzy dependency's URL is not an sdk-v* release asset: {url.group(1)}", file=sys.stderr)
        return 2
    print(version.group(1))
    return 0


def pin(zon: Path, url: str, hash_: str) -> int:
    text = zon.read_text()
    m = _fizzy_block(text)
    block = m.group(1)
    new_block, n_url = re.subn(r'(\.url\s*=\s*")[^"]*(")', rf"\g<1>{url}\g<2>", block)
    new_block, n_hash = re.subn(r'(\.hash\s*=\s*")[^"]*(")', rf"\g<1>{hash_}\g<2>", new_block)
    if n_url != 1 or n_hash != 1:
        sys.exit("the fizzy dependency needs exactly one .url and one .hash")
    zon.write_text(text[: m.start(1)] + new_block + text[m.end(1) :])
    return 0


def _semver(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def bump(zon: Path, sdk_version: str, released: str | None) -> int:
    text = zon.read_text()
    m = re.search(r'(\.version\s*=\s*")(\d+)\.(\d+)\.(\d+)(")', text)
    if not m:
        sys.exit("no `.version = \"X.Y.Z\"` in plugin.zig.zon")
    version = f"{m.group(2)}.{m.group(3)}.{m.group(4)}"
    if released and _semver(version) > _semver(released):
        new_version = version
    else:
        new_version = f"{m.group(2)}.{m.group(3)}.{int(m.group(4)) + 1}"
    text = text[: m.start()] + f"{m.group(1)}{new_version}{m.group(5)}" + text[m.end() :]
    text, n = re.subn(r'(\.min_sdk_version\s*=\s*")[^"]*(")', rf"\g<1>{sdk_version}\g<2>", text)
    if n != 1:
        sys.exit("no `.min_sdk_version` in plugin.zig.zon")
    zon.write_text(text)
    print(new_version)
    return 0


def released(manifest: Path) -> int:
    releases = json.loads(manifest.read_text()).get("releases", [])
    if releases:
        newest = max(releases, key=lambda r: _semver(r["version"]))
        print(newest["version"], newest.get("abi_fingerprint", ""))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        sys.exit(__doc__)
    cmd, path, rest = argv[1], Path(argv[2]), argv[3:]
    if cmd == "current" and not rest:
        return current(path)
    if cmd == "pin" and len(rest) == 2:
        return pin(path, *rest)
    if cmd == "bump" and len(rest) in (1, 2):
        return bump(path, rest[0], rest[1] if len(rest) == 2 else None)
    if cmd == "released" and not rest:
        return released(path)
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
