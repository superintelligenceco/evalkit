# Contributing to evalkit

Thanks for helping. This guide shows you how to set up the project, add a grader or a provider,
and open a pull request.

## Set up

You need Python 3.11 or later.

```sh
git clone https://github.com/superintelligenceco/evalkit.git
cd evalkit
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Every test runs offline. Tests use the `mock` provider or the local fake server in
`tests/conftest.py`, which speaks the OpenAI and Anthropic wire formats. Never add a test that
calls a paid API.

## Project layout

| Path | Contents |
| --- | --- |
| `src/evalkit/config.py` | Suite schema (pydantic models) and the YAML loader. |
| `src/evalkit/providers/` | Targets and judges: `mock`, `openai`, `anthropic`, `command`, `http`. |
| `src/evalkit/graders/` | Deterministic graders in `builtin.py`, LLM-as-judge in `judge.py`. |
| `src/evalkit/runner.py` | Concurrency, retries, caching, and repeats. |
| `src/evalkit/cache.py` | SQLite response cache. |
| `src/evalkit/results.py` | Result objects and the results JSON format. |
| `src/evalkit/report.py` | Terminal table, Markdown, JUnit XML, and badge JSON. |
| `src/evalkit/compare.py` | Baseline diff and regression gate. |
| `src/evalkit/cli.py` | The `evalkit` command. |
| `action.yml` | The composite GitHub Action. |
| `examples/` | Runnable suites. CI runs them through the action. |

## Checks

Run these before you push. CI runs the same commands on Python 3.11, 3.12, and 3.13.

```sh
ruff check .
ruff format --check .
mypy
pytest --cov
```

To fix formatting and safe lint issues automatically, run `ruff format . && ruff check --fix .`.

## Add a grader

1. Add a pydantic model to `config.py` with a `type: Literal["your_type"]` field and add it to
   the `GraderConfig` union.
2. Implement it in `graders/builtin.py` (or a new module) and dispatch to it in
   `graders/__init__.py`. Return a `Grade` with a `reason` that tells the reader what was wrong.
3. Add tests in `tests/test_graders.py` for a pass, a fail, and each option.
4. Document it in the graders reference in `README.md`.

## Add a provider

1. Add a config model to `config.py` and add it to the `ProviderConfig` union.
2. Implement `Provider` in `providers/`. Keep secrets out of `identity()`, since it feeds the
   cache key. Raise `ProviderError(retriable=True)` for timeouts, 429, and 5xx.
3. Extend the fake server in `tests/conftest.py` if the provider speaks HTTP, and add tests.

## Commits and pull requests

- Use [Conventional Commits](https://www.conventionalcommits.org/) for commit messages and PR
  titles, for example `feat(graders): add a rouge grader`. The release workflow builds the
  changelog from them.
- Keep each pull request focused on one change.
- Update `CHANGELOG.md` under `Unreleased` when behavior changes.

## Releases

The `Release` workflow (`.github/workflows/release.yml`) does two things:

- On every push to `main`, release-please opens or updates a release pull request that bumps the
  version and the changelog. When you merge that pull request, release-please creates the tag and
  the GitHub Release. A tag that `GITHUB_TOKEN` creates doesn't start other workflows, so the
  build jobs run inside the same workflow run, and only when release-please reports a new release.
- When you push a `vX.Y.Z` tag yourself, the same build jobs run, create the GitHub Release if
  the tag has none, and attach the artifacts.

Either way, the release gets the wheel, the sdist, the four standalone executables, and
`SHA256SUMS`, and the major version tag (for example `v0`) moves to the new release so
`superintelligenceco/evalkit@v0` resolves.

To build the artifacts without releasing, run the workflow by hand. The artifacts appear on the
workflow run only:

```sh
gh workflow run release.yml --ref main
```

To build an executable locally, install evalkit and PyInstaller, then run the build script. It
writes `dist/<name>` and smoke-tests it with `evalkit init` and `evalkit run` in an empty
directory:

```sh
pip install . pyinstaller
python scripts/build_binary.py evalkit-linux-x64
```

On Linux, PyInstaller needs `objdump` from binutils. The executable only runs on systems with the
same or a newer glibc than the build machine, which is why CI builds the Linux executables in a
Debian bullseye container.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating, you agree
to uphold it.
