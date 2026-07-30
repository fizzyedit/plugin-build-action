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
   checkout, so a `.path = "../../fizzy/sdk"` dependency fails there. Pin the **SDK release
   asset** for an `sdk-v*` tag (not the git archive of the monorepo — that pulls Velopack):

   ```zig
   .fizzy = .{
       .url = "https://github.com/fizzyedit/fizzy/releases/download/sdk-v0.1.42/fizzy-sdk-v0.1.42.tar.gz",
       .hash = "<zig-package-hash>", // zig fetch --save=fizzy <url>
   },
   ```

   That pin is the source of truth for `fizzy_sdk_version` and the ReleaseFast
   `abi_fingerprint` — the action reads both from the built dylib. You never copy them into
   workflow YAML. See fizzy's
   [`docs/PLUGINS.md`](https://github.com/fizzyedit/fizzy/blob/main/docs/PLUGINS.md) §2.3 / §5.

2. **Add identity-only `plugin.zig.zon`** at the repo root (`id` / `name` / `version` /
   `min_sdk_version`). The pushed tag (`vX.Y.Z`) **must equal** `.version`.

3. **Make `zig build` install the plugin dylib to `zig-out/<id>.<ext>`** — via
   `fizzy.plugin.create` + `.install` (generated dylib root; no author `root.zig`). If your build
   installs elsewhere, set `artifact-path`.

4. **Add the release workflow.** Copy [`examples/release.yml`](examples/release.yml) to your
   plugin repo as `.github/workflows/release.yml`:

   ```yaml
   name: Release
   on:
     push:
       tags: ["v*"]
   jobs:
     build:
       uses: fizzyedit/plugin-build-action/.github/workflows/build.yml@v3
       permissions:
         contents: write
       with:
         zig-version: "0.16.0"
   ```

5. **Register once in `fizzyedit/plugins`** — open a PR adding `registry/<id>.json` with
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

Bump the fizzy pin in `build.zig.zon` when you want a new SDK; the next tag's manifest picks up
the new `fizzy_sdk_version` / `abi_fingerprint` automatically. The manifest **accumulates**
releases (keyed by `version` + `abi_fingerprint`), so users on older SDKs keep matching an older
binary instead of seeing *"needs a rebuild."*

## Changelog

### v4 (pending — not yet tagged)

- `manifest.json` now carries top-level `name`/`description`/`tags`, read straight off the
  caller's `plugin.zig.zon` (`scripts/read_plugin_zon.py`) and passed through `assemble_manifest.py`'s
  new `--name`/`--description`/`--tags-json` args. This lets the `fizzyedit/plugins` aggregator
  fall back to these when a `registry/<id>.json` entry leaves its own `description`/`tags` blank,
  instead of requiring authors to hand-duplicate both.
- A tag bump (not just an additive change) because callers pin `uses: .../build.yml@v3`, and this
  file's own "Resolve plugin-build-action ref" step hardcodes the matching `ref="v3"` literal for
  its auxiliary script checkout — neither picks up new script behavior without the ref moving.

### v3

- Derive `fizzy_sdk_version` + `abi_fingerprint` from `zig-out/sdk-meta.json` (emitted by
  `fizzy.plugin.install`) — removed as workflow inputs.
- Cross-compile all 6 targets from `ubuntu-latest` (plugins are unsigned; no macOS/Windows
  runners or code signing).
- Read `id` / `version` / `min_sdk_version` from `plugin.zig.zon`; release version defaults to the
  triggering `v*` tag (must match the zon).
- Caller `release.yml` only needs `zig-version` (optional overrides for `id` / `version` /
  `artifact-path` / `targets` remain).

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
| `zig-version` | no | `0.16.0` | Zig toolchain version. |
| `id` | no | `plugin.zig.zon` `.id` | Override plugin id (must match the zon if set). |
| `version` | no | tag without `v` | Override release version (must match `plugin.zig.zon` `.version`). |
| `artifact-path` | no | `zig-out/<id>` | Built dylib path (relative to repo root) **without** extension. |
| `targets` | no | all 6 | Comma-separated `os_arch` subset to build. |

## How it works

- **Setup** reads `plugin.zig.zon`, checks the tag/`version` input against `.version`, and builds
  the target matrix.
- **One build per target across all 6 host arches**, all cross-compiled with `-Dtarget=` from
  `ubuntu-latest`. Plugins are unsigned pure Zig + vendored C (optional prebuilt `.a`/`.lib`
  deps are selected per target), so there is no macOS/Windows runner or signing step.
- Every target collects `zig-out/sdk-meta.json` (written by the fizzy pin at build time). Publish
  requires all targets to agree on sdk/fingerprint, then
  [`scripts/assemble_manifest.py`](scripts/assemble_manifest.py) merges the new release into the
  prior `manifest.json`.

## Files

| Path | Role |
|------|------|
| `.github/workflows/build.yml` | The reusable (`workflow_call`) build + publish workflow. |
| `scripts/assemble_manifest.py` | Merges per-target sha256 fragments into `manifest.json`. |
| `scripts/read_plugin_zon.py` | Parses identity from `plugin.zig.zon`. |
| `scripts/read_plugin_exports.py` | Optional local helper: `dlopen` a *native* plugin and print exports. |
| `examples/release.yml` | Drop-in caller for a plugin repo. |
