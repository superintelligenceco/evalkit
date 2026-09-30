# Quickstart

This page takes you from nothing to a passing suite, then to a regression gate. Every command here
runs offline, because the starter suite uses the built-in `mock` provider.

## Install evalkit

```sh
pip install sic-evalkit
```

Or install the standalone executable, which bundles Python:

```sh
curl -fsSL https://raw.githubusercontent.com/superintelligenceco/evalkit/main/install.sh | sh
```

Check the install:

```sh
evalkit --version
```

## Run the starter suite

```sh
mkdir my-evals && cd my-evals
evalkit init
evalkit run evals.yaml
```

`evalkit init` writes `evals.yaml`. `evalkit run` prints one row per task and exits with status 0
when the pass rate meets the suite's `fail_under` bar.

## Point it at a real model

Replace the `target` in `evals.yaml`:

```yaml
target:
  provider: openai          # any OpenAI-compatible API
  model: gpt-4o-mini        # reads OPENAI_API_KEY
```

For Anthropic models, use `provider: anthropic`, which reads `ANTHROPIC_API_KEY`. To test your own
program or service instead of a model, use a `command` or `http` target. See
[Concepts](concepts.md#targets).

## Save a baseline and catch a regression

```sh
evalkit run evals.yaml -o base.json          # on main
evalkit run evals.yaml -o head.json          # on your branch
evalkit compare base.json head.json --threshold 0.05
```

`compare` exits with status 1 when the pass rate or the mean score drops by more than the
threshold. To gate in one step, run `evalkit run evals.yaml --baseline base.json --threshold 0.05`.

## Next steps

- Add graders to your tasks: see the [suite file reference](reference/suite.md#graders).
- Run the suite on every pull request: see [CI integration](ci.md).
