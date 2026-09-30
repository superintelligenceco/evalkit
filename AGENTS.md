# AGENTS.md

Guidance for coding agents that work in this repository.

## Commands

- Install: `python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`
- Lint: `ruff check .` and `ruff format --check .`. Fix with `ruff format . && ruff check --fix .`.
- Typecheck: `mypy` (strict, configured in `pyproject.toml`)
- Test: `pytest` (add `--cov` for coverage)
- Try it: `evalkit run examples/quickstart/evals.yaml`

Run lint, typecheck, and test before you finish a change. All must pass.

## Conventions

- Python 3.11 or later, `from __future__ import annotations` in every module, full type hints.
- Runtime dependencies are `httpx`, `jsonschema`, `pydantic`, and `pyyaml`. Ask before adding one.
- Suite schema changes go in `config.py` and must keep `extra="forbid"`, so typos fail loudly.
- Every grader returns a `Grade` with a human-readable `reason`.
- Tests never call a paid API. Use the `mock` provider or the `fake_server` fixture.
- Commit messages follow Conventional Commits.

## Boundaries

- Don't commit `.venv/`, `dist/`, `.evalkit/`, coverage output, or generated reports.
- Don't weaken a test to make it pass. Fix the code or explain why the test was wrong.
- Don't put secrets, tokens, or machine-specific paths in fixtures or examples.
