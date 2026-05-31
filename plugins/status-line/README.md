# status-line

A configurable status-line HUD for [Claude Code](https://claude.com/claude-code):
model, project, git, a context-usage bar, and rate-limit windows - rendered on one
line (or expanded to several). Pure Python, standard library only, no dependencies.

```
[Opus 4.8] claude git:(main*) ctx ▰▰▱▱▱▱▱▱▱▱ 86k/1.0M 17% | 5h: 6% (2h 17m) | 7d: 44% (3d 6h)
```

## Install

From within Claude Code, with this marketplace added:

```
/plugin install status-line
/status-line:setup
```

`setup` picks the best available Python runtime (uv → `python -m venv` + pip →
system Python), wires the `statusLine` command into your `settings.json` (backing
up the existing one first), seeds a starter config, and shows a preview. Restart
Claude Code afterward so the new status line loads.

Requires Python 3.8+ **or** [uv](https://docs.astral.sh/uv/) on your PATH.

## Configure

```
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

## Preview

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

```bash
python3 -m unittest discover -s tests
```

## License

MIT
