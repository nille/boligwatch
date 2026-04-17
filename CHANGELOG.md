# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Fixed

- Re-listing detection now parses ISO 8601 dates instead of comparing strings, fixing incorrect results when timezone formats differ (`Z` vs `+00:00`).
- Added missing `--parking` and `--elevator` CLI flags (filters were already supported in config and MCP but had no argparse arguments).

### Changed

- Seen-file writes are now atomic (write to temp file, then rename) to prevent corruption if the process is killed mid-write during `--watch` mode.
- `SearchConfig.from_dict()` logs a warning when unknown keys are present in the config file, helping catch typos like `"max_rnet"`.
- `max_pages` is clamped to a ceiling of 50 to prevent accidental API abuse.
