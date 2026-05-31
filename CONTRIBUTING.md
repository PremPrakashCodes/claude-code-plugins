# Contributing

Thanks for helping improve this Claude Code plugin marketplace. Contributions of
all sizes are welcome: bug reports, docs fixes, new status-line styles, tests,
maintainer tooling, and new plugins.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Project Model

This repo is a marketplace first and a plugin host second:

- The root `.claude-plugin/marketplace.json` registers plugins.
- Each directory under `plugins/` is self-contained.
- Plugin runtime code, slash commands, scripts, tests, docs, and manifest files
  should stay inside that plugin's directory.
- Shared repository standards live at the root: CI, issue templates,
  contributing docs, changelog, license, and Makefile targets.

Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before making larger changes.

## Development Setup

The current `status-line` plugin has no runtime dependencies beyond Python's
standard library. Development tools are optional extras.

```bash
git clone git@github.com:PremPrakashCodes/claude-code-plugins.git
cd claude-code-plugins/plugins/status-line
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Quick local preview:

```bash
python3 src/statusline.py --demo
python3 src/statusline.py --styles
```

## Running Checks

From the repository root:

```bash
make test
make lint
make format-check
```

From the plugin directory:

```bash
python3 -m unittest discover -s tests
ruff check .
ruff format --check .
```

Run `ruff format .` to format code. CI runs tests, linting, and formatting on
Python 3.8 through 3.12.

## Coding Standards

- Keep `status-line` runtime code standard-library only.
- Preserve fail-silent behavior: the status line should print a blank line
  instead of breaking the user's prompt.
- Add or update tests for every behavior change.
- Keep user-facing configuration backwards compatible unless the changelog and
  version bump make a breaking change explicit.
- Use type hints for public functions and small docstrings where they clarify
  behavior or failure modes.
- Keep modules focused: data parsing in `hud/data.py`, configuration in
  `hud/config.py`, rendering in `hud/render.py`, terminal styling in
  `hud/colors.py`, git probing in `hud/gitinfo.py`.

## Pull Request Flow

1. Fork the repository and create a topic branch from `main`.
2. Make the smallest coherent change that solves the issue.
3. Add tests and update docs.
4. Update [CHANGELOG.md](CHANGELOG.md) under `[Unreleased]`.
5. Run `make check`.
6. Open a pull request using the template and link any related issue.

Use imperative commit messages, for example `Add smooth context bar tests`.

## Versioning

For plugin behavior changes, update both:

- `plugins/status-line/.claude-plugin/plugin.json`
- `plugins/status-line/pyproject.toml`

Use semantic versioning:

- Patch for bug fixes and docs that affect packaged plugin behavior.
- Minor for backwards-compatible features.
- Major for breaking config, command, or runtime behavior.

## Common Contributions

Add a bar style:

- Register a `(filled, empty)` glyph pair in `plugins/status-line/src/hud/bars.py`.
- Add coverage in `plugins/status-line/tests/test_bars.py`.
- Update the style list in `plugins/status-line/README.md` if needed.

Add a theme:

- Add an entry to `THEMES` in `plugins/status-line/src/hud/config.py`.
- Override only the roles that differ from `_BASE_ROLES`.
- Add or update render/config tests when behavior changes.

Add a preset:

- Add a partial config to `PRESETS` in `plugins/status-line/src/hud/config.py`.
- Keep presets small and composable.
- Document it in the plugin README.

Add a new plugin:

- Create `plugins/<name>/`.
- Include `.claude-plugin/plugin.json`, `README.md`, commands or runtime code,
  tests, and license metadata.
- Register it in `.claude-plugin/marketplace.json`.
- Add it to the root README plugin table.

## Reporting Issues

Use the issue templates in [.github/ISSUE_TEMPLATE](.github/ISSUE_TEMPLATE).
For `status-line` bugs, include:

- OS and shell
- Python version
- Claude Code version, if relevant
- Plugin version
- Steps to reproduce
- Output from `python3 src/statusline.py --demo`
- Relevant `config.json` snippets with secrets removed

## Maintainer Notes

Before merging:

- Check CI.
- Confirm docs match behavior.
- Confirm changelog and versions are appropriate.
- For release changes, install the plugin from the marketplace and run
  `/status-line:setup` in Claude Code.
