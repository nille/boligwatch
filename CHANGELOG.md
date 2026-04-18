# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added

- Cloudflare bypass via `curl_cffi` — when installed, API requests use Chrome TLS fingerprint impersonation to avoid Cloudflare bot challenges (HTTP 403). Install with `pip install curl_cffi`. Falls back to stdlib `urllib` when not installed.
- HTTP 403 errors are now retried with exponential backoff (previously only 429 and 5xx were retried).
- CI: ruff linting + formatting, mypy type checking, README badges.
- `pyproject.toml` with ruff and mypy configuration.

### Fixed

- `Z` suffix in ISO 8601 dates is now handled on Python 3.10 (where `fromisoformat()` doesn't support it natively).

- Re-listing detection now parses ISO 8601 dates instead of comparing strings, fixing incorrect results when timezone formats differ (`Z` vs `+00:00`).
- Added missing `--parking` and `--elevator` CLI flags (filters were already supported in config and MCP but had no argparse arguments).

### Changed

- Seen-file writes are now atomic (write to temp file, then rename) to prevent corruption if the process is killed mid-write during `--watch` mode.
- `SearchConfig.from_dict()` logs a warning when unknown keys are present in the config file, helping catch typos like `"max_rnet"`.
- `max_pages` is clamped to a ceiling of 50 to prevent accidental API abuse.
