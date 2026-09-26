# Changelog

All notable changes to this marketplace are documented here.

The format follows the spirit of [Keep a Changelog](https://keepachangelog.com/)
and plugin versions should follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Open-source project documentation, contribution guidance, community standards,
  templates, and development quality checks.
- `agent-router` plugin: AI-classified model routing for Claude's subagent
  dispatches. Rewrites each dispatch's model to the cheapest capable tier and
  logs every routing decision and its cost locally.
- `status-line` `router` segment: shows the current session's routed dispatches
  and estimated net savings from `agent-router` (opt-in via `segments`).

## [0.1.0] - 2026-05-31

### Added

- Initial `status-line` Claude Code plugin with model, project, git, context,
  usage, cost, and session segments.
- Cross-platform setup scripts for Unix-like shells and PowerShell.
- Standard-library Python implementation with unit tests.
