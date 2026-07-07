# plugin-build-action

Build action for fizzy plugins.

A reusable GitHub Actions workflow that builds a [Fizzy](https://github.com/fizzyedit/fizzy)
plugin for every supported target, hashes each binary, assembles the author `manifest.json`, and
publishes both as **GitHub Release assets**.

A Fizzy plugin is a native dylib valid for exactly one `(abi_fingerprint, os-arch)` pair, so a
release ships one binary per target plus a manifest the in-app store reads — indirectly, via the
[`fizzyedit/plugins`](https://github.com/fizzyedit/plugins) aggregator, which folds every
author's manifest into a static catalog served at `https://plugins.fizzyed.it/catalog/`. This
action automates the build matrix so you don't hand-build, hand-hash, and hand-write the
manifest each release.

```
tag v0.1.0  ──►  build.yml  ──►  per-target dylib + sha256
                     │
                     ▼  assemble_manifest.py (accumulates prior releases)
            release assets: pixi-macos-aarch64.dylib, …, manifest.json
                     │
                     ▼  registry/<id>.json points manifest_url at releases/latest
            fizzyedit/plugins aggregator  ──►  catalog/ (summary.json + per-fingerprint
                                                 releases.json)  ──►  Fizzy store
```

## What it produces

For a tag like `v0.1.0`, the release gets:

```
<id>-macos-aarch64.dylib     <id>-macos-x86_64.dylib
<id>-linux-x86_64.so         <id>-linux-aarch64.so
<id>-windows-x86_64.dll      <id>-windows-aarch64.dll
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

   Pick the commit whose `src/sdk/version.zig` has the `sdk_version` you're building against (run
   `zig fetch --save=fizzy <url>` to fill in the hash). `abi-fingerprint` below is that commit's
   **runtime** `dylib.abi_fingerprint` in `ReleaseFast` mode — not the CI-lock
   `recorded_sdk_shape_fingerprint` in the same file. See fizzy's
   [`docs/PLUGINS.md`](https://github.com/fizzyedit/fizzy/blob/main/docs/PLUGINS.md) §5 for the
   distinction.

2. **Make `zig build` install the plugin dylib to `zig-out/<id>.<ext>`** — the canonical layout via
   `root.zig` + `sdk.dylib.exportEntry`. If your build installs elsewhere, set `artifact-path`.

3. **Add the release workflow.** Copy [`examples/release.yml`](examples/release.yml) to your
   plugin repo as `.github/workflows/release.yml` and fill in the inputs. The **version is the
   pushed tag** (`vX.Y.Z` → `X.Y.Z`) — you never edit a version string here, so it can't drift
   from the tag:

   ```yaml
   name: Release
   on:
     push:
       tags: ["v*"]
   jobs:
     version:                      # tag → version (v0.1.2 → 0.1.2); single source of truth
       runs-on: ubuntu-latest
       outputs:
         version: ${{ steps.v.outputs.version }}
       steps:
         - id: v
           run: echo "version=${GITHUB_REF_NAME#v}" >> "$GITHUB_OUTPUT"
     build:
       needs: version
       uses: fizzyedit/plugin-build-action/.github/workflows/build.yml@v2
       permissions:
         contents: write          # create the release + upload assets
       with:
         id: pixi                  # must equal your manifest id and the registry/<id>.json stem
         version: ${{ needs.version.outputs.version }}  # from the tag — do not hardcode
         fizzy-sdk-version: "0.9.0"       # example — use YOUR pinned fizzy commit's sdk_version
         abi-fingerprint: "0x17428bfc3819460c"  # and its runtime ReleaseFast abi_fingerprint
         min-sdk-version: "0.9.0"
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
plugin into the catalog. Subsequent releases need no registry PR — just tag again.

## Changelog

### v2

- Pre-fetch Zig package dependencies with retries before building, working around Zig 0.16
  `HttpConnectionClosing` flakes when fetching GitHub deps (especially on Windows CI).
- Use a workspace-local `ZIG_GLOBAL_CACHE_DIR` and pre-create cache `tmp/` (fixes cold-cache
  zip-fetch `FileNotFound` on CI).

### v1

Initial release.

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `id` | yes | — | Plugin id; must equal the manifest id and the `registry/<id>.json` stem. |
| `version` | yes | — | Release version, no leading `v` (e.g. `0.1.0`). The tag is `v<version>`. The `examples/release.yml` caller derives this from the pushed tag, so don't hardcode it. |
| `fizzy-sdk-version` | yes | — | Fizzy SDK version this build targets (e.g. `0.9.0` — your pinned commit's `sdk_version`). |
| `abi-fingerprint` | yes | — | Host ABI fingerprint hex; must match your pinned commit's runtime `ReleaseFast` fingerprint (e.g. `0x17428bfc3819460c`). |
| `min-sdk-version` | no | = `fizzy-sdk-version` | Minimum SDK version required to load. |
| `zig-version` | no | `0.16.0` | Zig toolchain version. |
| `artifact-path` | no | `zig-out/<id>` | Built dylib path (relative to repo root) **without** extension. |

Bump `fizzy-sdk-version` / `abi-fingerprint` only when you rebuild against a new Fizzy SDK — they
change on a deliberate SDK bump, not every app release. The manifest **accumulates** releases
(keyed by `version` + `abi_fingerprint`), so users on older SDKs keep matching an older binary
instead of seeing *"needs a rebuild."*

## How it works

- **One build per target across all 6 host arches**, cross-compiled with `-Dtarget=` from three
  runners (`macos-14` → macos-{aarch64,x86_64}, `ubuntu-latest` → linux-{x86_64,aarch64},
  `windows-latest` → windows-{x86_64,aarch64}). Plugins are pure Zig + vendored C, so the
  non-native arches cross-compile cleanly — no scarce arm64 runners needed.
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
