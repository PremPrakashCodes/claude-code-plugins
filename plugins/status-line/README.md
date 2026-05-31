# status-line

A configurable status-line HUD for [Claude Code](https://claude.com/claude-code):
model, project, git, a context-usage bar, and rate-limit windows - rendered on one
line (or expanded to several). Pure Python, standard library only, no dependencies.

```
[Opus 4.8] claude git:(main*) ctx ▰▰▱▱▱▱▱▱▱▱ 86k/1.0M 17% | 5h: 6% (2h 17m) | 7d: 44% (3d 6h)
```

## Install

From within Claude Code, with this marketplace added:

```text
/plugin install status-line
/status-line:setup
```

`setup` picks the best available Python runtime (uv → `python -m venv` + pip →
system Python), wires the `statusLine` command into your `settings.json` (backing
up the existing one first), seeds a starter config, and shows a preview. Restart
Claude Code afterward so the new status line loads.

Requires Python 3.8+ **or** [uv](https://docs.astral.sh/uv/) on your PATH.

## Features

- Model and project context at a glance.
- Git branch, dirty state, ahead/behind counts, and optional file stats.
- Context window usage with selectable progress-bar styles.
- 5-hour and 7-day rate-limit windows with reset countdowns.
- Optional cost, duration, and line-change session details.
- Compact one-line layout or expanded multi-line layout.
- Themes, custom colors, custom labels, and partial config overrides.
- Fail-silent runtime behavior so prompt rendering is never interrupted by a
  traceback.

## Configure

```text
/status-line:configure
```

Or edit the config file directly - it is **deep-merged over the built-in
defaults**, so you only set the keys you want to change:

```
$CLAUDE_CONFIG_DIR/plugins/status-line/config.json   (~/.claude/... by default)
```

The authoritative list of options, themes, and presets lives in
[`src/hud/config.py`](src/hud/config.py) (`DEFAULTS`, `THEMES`, `PRESETS`).

| Key | What it controls |
|-----|------------------|
| `segments` | Which segments to show and in what order: `model, project, git, context, usage, cost, session` |
| `layout` | `compact` (one line) or `expanded` (one segment per line) |
| `theme` | `default, nord, dracula, gruvbox, mono` - or override individual roles under `colors` |
| `context.barStyle` | `rounded, blocks, shade, bars, dots, line, equals, hash, ascii, arrows, smooth, braille` |
| `context.value` | `tokens` (86k/1.0M), `percent`, `both`, or `none` |
| `usage.windows` | Subset of `["5h", "7d"]`; rename via `usage.labels` |
| `*.warnThreshold` / `*.critThreshold` | Percent at which the color escalates |

Presets: `minimal` (model + context %), `essential` (the default set), `full`
(adds cost + session lines and git file stats).

### Example Config

User config is partial. This is enough to switch theme, show context percent,
and relabel the weekly usage window:

```json
{
  "theme": "nord",
  "context": {
    "value": "both",
    "barStyle": "smooth"
  },
  "usage": {
    "labels": {
      "7d": "weekly"
    }
  }
}
```

## Preview

Run the non-installed previews from the `plugins/status-line` directory:

```bash
# installed console script
status-line --demo
# or, no install, any Python 3.8+
python3 src/statusline.py --demo
# preview a specific config file
status-line --demo --config /path/to/config.json
# list bar styles
status-line --styles
```

The HUD reads Claude Code's status-line JSON payload on stdin; `--demo` renders
sample data instead. It is fail-silent by design - any error prints a blank line
rather than crashing your prompt.

## Develop

Create a local environment:

```bash
cd plugins/status-line
python3 -m venv .venv
source .venv/bin/activate
# Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Run tests and quality checks:

```bash
python3 -m unittest discover -s tests
ruff check .
ruff format --check .
```

The runtime package is intentionally small:

| Module | Responsibility |
| ------ | -------------- |
| `hud/cli.py` | CLI entry point, demo payload, stdin handling |
| `hud/data.py` | Tolerant parsing of Claude Code status-line JSON |
| `hud/config.py` | Defaults, themes, presets, config loading |
| `hud/render.py` | Segment composition, truncation, per-segment isolation |
| `hud/colors.py` | ANSI color parsing, control-character stripping |
| `hud/bars.py` | Progress bar styles |
| `hud/gitinfo.py` | Best-effort git status probing |

See the repository [architecture guide](../../docs/ARCHITECTURE.md) for broader
maintainer guidance.

## Troubleshooting

- Run `python3 src/statusline.py --demo` to check whether the renderer works
  outside Claude Code.
- Run `python3 src/statusline.py --styles` to confirm the installed runtime is
  the expected version.
- Re-run `/status-line:setup` after plugin updates so the stable runtime under
  `$CLAUDE_CONFIG_DIR/plugins/status-line/.venv` is refreshed.
- If output is blank, temporarily preview with `--demo --config /path/to/config`
  and check whether the config file is valid JSON.

## License

MIT
