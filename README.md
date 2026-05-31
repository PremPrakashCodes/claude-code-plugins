# Claude Code Plugin Marketplace

A small, contributor-friendly [Claude Code](https://claude.com/claude-code)
plugin marketplace. The repository is organized as a marketplace shell with
self-contained plugins under `plugins/`.

## Add This Marketplace

In Claude Code:

```text
/plugin marketplace add PremPrakashCodes/claude-code-plugins
```

Then install a plugin from the marketplace:

```text
/plugin install status-line
/reload-plugins
/status-line:setup
```

## Plugins

| Plugin | Description |
| ------ | ----------- |
| [status-line](plugins/status-line) | Configurable status-line HUD for Claude Code: model, project, git, context usage, rate-limit windows, cost, and session details. Pure Python, standard library only. |

The HUD renders a compact, single-line view of your session:

```text
[Opus 4.8] | claude | ctx ▰▱▱▱▱▱▱▱▱▱ 86k/1.0M | 5h: 6% (2h 16m) | 7d: 44% (3d 5h)
```

Preview it yourself without installing — see
[Preview the status line](#development-setup).

## Repository Layout

```text
.
|-- .claude-plugin/              # Marketplace manifest
|-- .github/                     # Issue templates, PR template, CI
|-- docs/                        # Architecture and maintainer docs
|-- plugins/
|   `-- status-line/             # Self-contained Claude Code plugin
|       |-- .claude-plugin/      # Plugin manifest
|       |-- commands/            # Claude slash-command prompts
|       |-- scripts/             # Cross-platform setup helpers
|       |-- src/hud/             # Runtime package
|       `-- tests/               # Unit tests
|-- CHANGELOG.md
|-- CODE_OF_CONDUCT.md
|-- CONTRIBUTING.md
|-- LICENSE
|-- Makefile
`-- README.md
```

Each plugin should keep its runtime code, tests, docs, commands, and install
helpers inside its own directory. Register new plugins in
[`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json).

## Development Setup

Prerequisites:

- Python 3.8 or newer
- `git`
- Optional: [`uv`](https://docs.astral.sh/uv/) for faster local tooling

Set up the current plugin for development:

```bash
git clone git@github.com:PremPrakashCodes/claude-code-plugins.git
cd claude-code-plugins/plugins/status-line
python3 -m venv .venv
source .venv/bin/activate
# Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Preview the status line without installing it into Claude Code:

```bash
# from plugins/status-line/
python3 src/statusline.py --demo
python3 src/statusline.py --styles
```

## Quality Checks

From the repository root:

```bash
make test
make lint
make format-check
```

Or from `plugins/status-line`:

```bash
python3 -m unittest discover -s tests
ruff check .
ruff format --check .
```

Use `make format` or `ruff format .` before opening a pull request.

## Release And Deployment

This repository is deployed by pushing marketplace and plugin changes to the
default branch. Claude Code reads the marketplace manifest from the repository,
and each plugin is installed from its registered `source` path.

Release checklist:

1. Update the plugin version in
   [`plugins/status-line/.claude-plugin/plugin.json`](plugins/status-line/.claude-plugin/plugin.json)
   and [`plugins/status-line/pyproject.toml`](plugins/status-line/pyproject.toml)
   when behavior changes.
2. Update [CHANGELOG.md](CHANGELOG.md) under `[Unreleased]`, then add a dated
   release section.
3. Run `make check`.
4. Push to `main` after review.
5. Verify installation in Claude Code with `/plugin install status-line`,
   `/reload-plugins`, and `/status-line:setup`.

## Documentation

- [status-line README](plugins/status-line/README.md) - user-facing install,
  configuration, preview, and development guide.
- [Architecture](docs/ARCHITECTURE.md) - project boundaries, runtime flow, and
  extension points.
- [Contributing](CONTRIBUTING.md) - local workflow, coding standards, and PR
  expectations.
- [Code of Conduct](CODE_OF_CONDUCT.md) - community standards.

## License

MIT. See [LICENSE](LICENSE).
