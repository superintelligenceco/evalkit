# Changelog

All notable changes to this project are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Standalone `evalkit` executables for Linux x64, Linux arm64, macOS on Apple silicon, and
  Windows x64. They bundle Python, so you can run evalkit without installing Python.
- Every GitHub Release carries the executables, the wheel and sdist, and a `SHA256SUMS` file.
- A multi-arch container image on `ghcr.io/superintelligenceco/evalkit`, signed with cosign.
  Its working directory holds the starter suite, so `docker run` works without a mount.
- Releases carry SPDX SBOMs and build provenance attestations for the executables, the wheel, the
  sdist, and the image.
- The release workflow moves a major version tag, such as `v0`, so workflows can use
  `superintelligenceco/evalkit@v0`.

### Changed

- You release by pushing a `vX.Y.Z` tag. The release-please pull request flow is gone.

### Fixed

- The CodeQL workflow now has the `actions: read` permission it needs in private repositories,
  and keeps the SARIF as a workflow artifact when code scanning isn't available.

## [0.1.0] - 2026-09-30

The first release. evalkit runs YAML eval suites against models or your own app, grades the
output, and gates CI on pass rate and regressions.

### Added

- Suite files in YAML or JSON with strict validation and readable errors, tasks inline or from
  `.yaml`, `.json`, or `.jsonl` files, `{{ var }}` prompt templates, and `${VAR}` expansion in
  provider settings.
- Graders: `exact`, `contains`, `regex`, `json_schema` (inline or file, extracts JSON from code
  fences and prose), `numeric` with absolute and relative tolerance, custom `python` functions
  (sync or async), and `llm_judge` with a rubric and a pluggable judge provider. Any grader can be
  negated and weighted.
- Providers: `openai` (any OpenAI-compatible API), `anthropic`, `command`, `http`, and a
  deterministic `mock` provider with regex rules, simulated flakiness, latency, and transient
  failures.
- Runner with bounded concurrency, retries with exponential backoff on timeouts, 429, and 5xx, a
  SQLite response cache, `repeat` for flakiness stats, and per-task token, cost, and latency
  tracking.
- Reports: terminal table, results JSON, JUnit XML, GitHub-flavored Markdown, and a shields.io
  endpoint badge.
- `evalkit compare` and `evalkit run --baseline` to fail CI when the pass rate or score drops
  beyond a threshold, or, in strict mode, when any task regresses.
- `evalkit validate`, `evalkit init`, `evalkit schema`, and `evalkit cache`.
- A composite GitHub Action that runs a suite, writes the job summary, and exposes the pass rate
  as outputs.
- Example suites: `quickstart`, `support-bot`, `flaky`, and `openai-compatible`.

[Unreleased]: https://github.com/superintelligenceco/evalkit/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/superintelligenceco/evalkit/releases/tag/v0.1.0
