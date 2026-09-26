# Architecture

This repository is a Claude Code plugin marketplace. The root exists to publish
and govern plugins; each plugin owns its runtime and contributor surface.

## Boundaries

```text
Marketplace root
|-- .claude-plugin/marketplace.json  # Lists available plugins
|-- .github/                         # Community and CI automation
|-- docs/                            # Shared maintainer documentation
`-- plugins/<plugin>/                # Self-contained plugin packages
```

Keep cross-plugin concerns at the root. Keep plugin-specific behavior, tests,
commands, setup scripts, and docs inside the plugin directory.

## status-line Runtime

The `status-line` plugin is a Python package with no runtime dependencies. It is
designed to run on every Claude Code status-line refresh, so startup cost and
failure handling matter.

Runtime flow:

1. Claude Code invokes the configured command and pipes a JSON payload to stdin.
2. `src/statusline.py` or the installed `status-line` console script delegates
   to `hud.cli:main`.
3. `hud.data.read_payload()` reads stdin and `hud.data.parse()` extracts a
   tolerant `HudData` model.
4. `hud.config.load()` deep-merges user config over defaults, then
   `hud.config.resolve_theme()` applies color overrides.
5. `hud.render.render()` calls segment renderers in configured order.
6. Each segment may fail independently; broken or unavailable segments are
   skipped.
7. Compact output is truncated by dropping trailing cells when terminal width is
   known.

## Design Principles

- Runtime code uses only Python's standard library.
- User config is partial and deep-merged over defaults.
- Rendering is fail-silent: blank or degraded output is better than a prompt
  traceback.
- Git integration is best-effort and bounded by short subprocess timeouts.
- Tests should be deterministic, stripping ANSI codes and pinning time when
  needed.

## Extension Points

Add a new segment:

1. Extend `HudData` in `hud/data.py` only if the segment needs parsed payload
   state.
2. Add a `_seg_<name>` renderer in `hud/render.py`.
3. Register it in `_RENDERERS`.
4. Add default config in `hud/config.py`.
5. Add render tests for enabled, disabled, missing-data, and failure cases.
6. Document the segment in `plugins/status-line/README.md`.

Add a new config option:

1. Add a conservative default to `DEFAULTS`.
2. Read it with `.get()` or rely on the deep-merged default when appropriate.
3. Add tests for partial user config so backwards compatibility stays clear.
4. Update README tables and command guidance if the option is user-facing.

Add a new plugin:

1. Create `plugins/<name>/` with `.claude-plugin/plugin.json`.
2. Keep plugin implementation and tests inside that directory.
3. Register the plugin in `.claude-plugin/marketplace.json`.
4. Add root README and changelog entries.

## Release Flow

1. Land changes through a pull request.
2. Keep `[Unreleased]` in `CHANGELOG.md` current.
3. Bump plugin versions for behavior changes.
4. Run `make check`.
5. Merge to `main`.
6. Verify installation from Claude Code.
