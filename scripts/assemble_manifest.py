#!/usr/bin/env python3
"""Merge per-target sha256 fragments into a Fizzy plugin `manifest.json`.

Each build job emits one fragment `{ "os_arch", "url", "sha256" }`; this collects them into a
single release with the shared identity metadata (version, abi_fingerprint, sdk versions), plus
top-level `name`/`description`/`tags` straight off `plugin.zig.zon`. The output schema is exactly
what `fizzyedit/plugins` aggregates (falling back to these when a `registry/<id>.json` entry
leaves its own copies blank — see that repo's `store/src/ingest.zig`) and what Fizzy's store reads
(see the host's `src/backend/plugin_store/registry.zig`). Stdlib only.
"""
from __future__ import annotations

import argparse
import datetime
import json
import urllib.request
from pathlib import Path


def fetch_existing_releases(url: str, plugin_id: str) -> list[dict]:
    """Best-effort fetch of the previously published manifest's releases (for accumulation).
    A 404 (first release) or any error yields an empty list — we just start fresh."""
    if not url:
        return []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "plugin-build-action/1"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            prev = json.loads(resp.read().decode("utf-8"))
        if isinstance(prev, dict) and prev.get("id") == plugin_id:
            rels = prev.get("releases")
            return rels if isinstance(rels, list) else []
    except Exception as e:  # noqa: BLE001 — first release / outage is fine
        print(f"note: no prior manifest merged ({e})")
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--id", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--abi-fingerprint", required=True)
    ap.add_argument("--fizzy-sdk-version", required=True)
    ap.add_argument("--min-sdk-version", required=True)
    ap.add_argument("--name", default="", help="plugin.zig.zon .name (optional, informational)")
    ap.add_argument("--description", default="", help="plugin.zig.zon .description (optional)")
    ap.add_argument("--tags-json", default="[]", help="plugin.zig.zon .tags as a JSON array (optional)")
    ap.add_argument("--author", default="", help="plugin.zig.zon .author (optional, cosmetic)")
    ap.add_argument("--author-url", default="", help="plugin.zig.zon .author_url (optional)")
    ap.add_argument("--frags", required=True, help="directory of <os-arch>.json fragments")
    ap.add_argument("--out", required=True)
    ap.add_argument("--published", default=datetime.date.today().isoformat())
    ap.add_argument("--merge-url", default="",
                    help="prior manifest.json URL to accumulate releases from (never rewrite history)")
    args = ap.parse_args()

    tags = json.loads(args.tags_json)
    if not isinstance(tags, list):
        raise SystemExit(f"--tags-json must be a JSON array, got: {args.tags_json!r}")

    downloads: dict[str, dict] = {}
    for frag_path in sorted(Path(args.frags).glob("*.json")):
        frag = json.loads(frag_path.read_text())
        os_arch = frag["os_arch"]
        downloads[os_arch] = {"url": frag["url"], "sha256": frag["sha256"]}

    if not downloads:
        raise SystemExit(f"no fragments found in {args.frags}")

    new_release = {
        "version": args.version,
        "min_sdk_version": args.min_sdk_version,
        "abi_fingerprint": args.abi_fingerprint,
        "fizzy_sdk_version": args.fizzy_sdk_version,
        "published": args.published,
        "downloads": downloads,
    }

    # Accumulate: keep prior releases, replace any with the same (version, abi_fingerprint).
    key = (args.version, args.abi_fingerprint)
    releases = [
        r for r in fetch_existing_releases(args.merge_url, args.id)
        if (r.get("version"), r.get("abi_fingerprint")) != key
    ]
    releases.append(new_release)

    manifest = {
        "id": args.id,
        "name": args.name,
        "description": args.description,
        "tags": tags,
        "author": args.author,
        "author_url": args.author_url,
        "releases": releases,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {out} with {len(downloads)} download(s): {', '.join(sorted(downloads))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
