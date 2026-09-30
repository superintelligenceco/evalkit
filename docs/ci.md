# CI integration

## GitHub Actions

```yaml
name: Evals
on: [pull_request]
permissions:
  contents: read
jobs:
  evals:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: superintelligenceco/evalkit@v0
        id: evals
        with:
          suite: evals.yaml
          python-version: "3.12"
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
      - run: echo "Pass rate ${{ steps.evals.outputs.pass-rate }}"
```

The release workflow moves a major version tag, such as `v0`, to each new release, so
`superintelligenceco/evalkit@v0` tracks the latest 0.x release. Pin the action to a full commit
SHA in production workflows. The action writes `results.json`,
`junit.xml`, `summary.md`, and `badge.json` to `output-dir` (default `evalkit-results`) and appends
the Markdown summary to the job summary.

| Input | Default | Description |
| --- | --- | --- |
| `suite` | required | Path to the suite file. |
| `baseline` | | Results JSON to compare against. |
| `threshold` | `0` | Allowed drop against the baseline, as a fraction. |
| `strict` | `false` | Fail when any single task regresses. |
| `fail-under` | | Minimum pass rate. Overrides the suite setting. |
| `output-dir` | `evalkit-results` | Where the reports go. |
| `args` | | Extra `evalkit run` arguments, such as `--tag smoke`. |
| `python-version` | | Install this Python first. Leave empty to use the runner's `python3`. |
| `install` | the action's own copy | A pip requirement to install instead. |
| `job-summary` | `true` | Write the Markdown summary to the job summary. |

Outputs: `passed`, `total`, `pass-rate`, `ok`, and `results-file`.

This repository runs its own examples through the action on every push. See
[`.github/workflows/evals.yml`](https://github.com/superintelligenceco/evalkit/blob/main/.github/workflows/evals.yml).

## Baselines in CI

A simple pattern: upload `results.json` as an artifact on `main`, download the latest one in pull
request workflows, and pass it as `baseline`. The response cache makes the main-branch run cheap,
and you can cache `.evalkit/` between jobs with `actions/cache` to skip repeat API calls.

## Other CI systems

Run the CLI and publish the JUnit file with your system's test report feature. Download a
[release executable](index.md#install) or install with pip:

```sh
pip install sic-evalkit
evalkit run evals.yaml --junit evalkit-junit.xml -o results.json
```

## Badge

`--badge badge.json` writes a shields.io endpoint badge such as
`{"schemaVersion": 1, "label": "evals", "message": "7/8 passed", "color": "yellow"}`. Publish the
file anywhere public, such as GitHub Pages or a gist, and point
`https://img.shields.io/endpoint?url=<url-of-badge.json>` at it.

## Results format

`-o results.json` writes everything evalkit knows about a run: the suite, target, seed, a summary
(pass rate, score, flaky and errored counts, tokens, cost, p50 and p95 latency, cached runs), and
every task with every run, output, grade, and reason. `format: 1` versions the layout.
`compare` reads only the summary and each task's `id`, `status`, `passed`, and `score`.
