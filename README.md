# plugin-build-action

Build action for fizzy plugins.

A reusable GitHub Actions workflow that builds a [Fizzy](https://github.com/fizzyedit/fizzy)
plugin for every supported target, hashes each binary, assembles the author `manifest.json`, and
publishes both as **GitHub Release assets**.

A Fizzy plugin is a native dylib valid for exactly one `(abi_fingerprint, os-arch)` pair, so a
release ships one binary per target plus a manifest the in-app store reads — indirectly, via the
[`fizzyedit/plugins`](https://github.com/fizzyedit/plugins) aggregator, which merges every
author's manifest into `https://plugins.fizzyed.it/index.json`. This action automates that matrix
so you don't hand-build, hand-hash, and hand-write the manifest each release.

```
tag v0.1.0  ──►  build.yml  ──►  per-target dylib + sha256
                     │
                     ▼  assemble_manifest.py (accumulates prior releases)
            release assets: pixi-macos-aarch64.dylib, …, manifest.json
                     │
                     ▼  registry/<id>.json points manifest_url at releases/latest
            fizzyedit/plugins aggregator  ──►  index.json  ──►  Fizzy store
```

## What it produces

For a tag like `v0.1.0`, the release gets:

```
<id>-macos-aarch64.dylib
<id>-linux-x86_64.so
<id>-windows-x86_64.dll
manifest.json            ← references the binaries above (url + sha256), accumulating older releases
```

## Setup (once per plugin repo)

1. **Pin the Fizzy SDK by URL in your `build.zig.zon`** — *not* a local `path`. CI has no sibling
   checkout, so a `.path = "../../fizzy"` dependency fails there. Use a fetchable archive:

   ```zig
   .fizzy = .{
       .url = "https://github.com/fizzyedit/fizzy/archive/<commit>.tar.gz",
       .hash = "<zig-package-hash>",
   },
   ```

   Pick the commit whose `src/sdk/version.zig` has the `sdk_version` / `recorded_abi_fingerprint`
   you're building against (run `zig fetch --save=fizzy <url>` to fill in the hash).

2. **Make `zig build` install the plugin dylib to `zig-out/<id>.<ext>`** — the canonical layout via
   `root.zig` + `sdk.dylib.exportEntry`. If your build installs elsewhere, set `artifact-path`.

3. **Add the release workflow.** Copy [`examples/release.yml`](examples/release.yml) to your
   plugin repo as `.github/workflows/release.yml` and fill in the inputs:

   ```yaml
   name: Release
   on:
     push:
       tags: ["v*"]
   jobs:
     build:
       uses: fizzyedit/plugin-build-action/.github/workflows/build.yml@v1
       permissions:
         contents: write          # create the release + upload assets
       with:
         id: pixi                  # must equal your manifest id and the registry/<id>.json stem
         version: "0.1.0"          # plugin release version, no leading v
         fizzy-sdk-version: "0.7.0"
         abi-fingerprint: "0x1bb54eb7506cbd78"
         min-sdk-version: "0.7.0"
         zig-version: "0.16.0"
   ```

4. **Register once in `fizzyedit/plugins`** — open a PR adding `registry/<id>.json` with
   `manifest_url` pointing at your latest release manifest:

   ```json
   {
     "id": "pixi",
     "name": "Pixi",
     "description": "Pixel-art editor for Fizzy.",
     "author": "foxnne",
     "homepage": "https://github.com/fizzyedit/pixi",
     "tags": ["editor", "pixel-art"],
     "manifest_url": "https://github.com/fizzyedit/pixi/releases/latest/download/manifest.json"
   }
   ```

## Releasing

```sh
git tag v0.1.0 && git push origin v0.1.0
```

The workflow builds all targets, publishes the release with the binaries + `manifest.json`, and
the next `fizzyedit/plugins` aggregation (on merge, its 6-hourly cron, or a manual run) pulls your
plugin into the index. Subsequent releases need no registry PR — just tag again.

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `id` | yes | — | Plugin id; must equal the manifest id and the `registry/<id>.json` stem. |
| `version` | yes | — | Release version, no leading `v` (e.g. `0.1.0`). The tag is `v<version>`. |
| `fizzy-sdk-version` | yes | — | Fizzy SDK version this build targets (e.g. `0.7.0`). |
| `abi-fingerprint` | yes | — | Host ABI fingerprint hex; must match the SDK (e.g. `0x1bb54eb7506cbd78`). |
| `min-sdk-version` | no | = `fizzy-sdk-version` | Minimum SDK version required to load. |
| `zig-version` | no | `0.16.0` | Zig toolchain version. |
| `artifact-path` | no | `zig-out/<id>` | Built dylib path (relative to repo root) **without** extension. |

Bump `fizzy-sdk-version` / `abi-fingerprint` only when you rebuild against a new Fizzy SDK — they
change on a deliberate SDK bump, not every app release. The manifest **accumulates** releases
(keyed by `version` + `abi_fingerprint`), so users on older SDKs keep matching an older binary
instead of seeing *"needs a rebuild."*

## How it works

- **Native build per target** (`macos-14` → macos-aarch64, `ubuntu-latest` → linux-x86_64,
  `windows-latest` → windows-x86_64), so SDL/dvui/cmark link cleanly — no cross-compilation.
- Each job emits a `{ os_arch, url, sha256 }` fragment; the `publish` job runs
  [`scripts/assemble_manifest.py`](scripts/assemble_manifest.py), which fetches the previous
  `releases/latest/.../manifest.json` and merges the new release in (replacing any entry with the
  same `version` + `abi_fingerprint`), then `softprops/action-gh-release` uploads everything.

## Files

| Path | Role |
|------|------|
| `.github/workflows/build.yml` | The reusable (`workflow_call`) build + publish workflow. |
| `scripts/assemble_manifest.py` | Merges per-target sha256 fragments into `manifest.json` (stdlib only). |
| `examples/release.yml` | Drop-in caller for a plugin repo. |
