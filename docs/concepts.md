# Concepts

## Suites

A suite is a YAML (or JSON) file that lives in your repository next to the code it tests. It names
a target, lists tasks, and attaches graders. Unknown keys are errors, so a typo fails loudly
instead of silently disabling a check. Run `evalkit validate evals.yaml` to check a file without
running it.

## Tasks

A task is one input plus the checks its output must pass. Tasks can live inline in the suite or in
a separate `.yaml`, `.json`, or `.jsonl` file, which is convenient for datasets. Each task has an
`id`, an `input` or `vars` for the prompt template, an optional `expected` value, `tags` for
selection, and its own graders.

## Targets

The target is what you evaluate:

- **A model:** `openai` (OpenAI and any compatible API, including gateways and local servers) or
  `anthropic`.
- **Your program:** `command` runs a process and sends the prompt on stdin.
- **Your service:** `http` posts a templated JSON body to your endpoint and reads the answer from
  the response.
- **Nothing at all:** `mock` returns canned or echoed answers. It's deterministic and offline,
  which makes it the right target for demos and for testing a suite itself.

Testing your app instead of the bare model means you grade what your users actually see, after
retrieval, tools, and post-processing.

## Graders

A grader turns one output into a verdict: pass or fail, a score from 0 to 1, and a reason. evalkit
ships `exact`, `contains`, `regex`, `json_schema`, `numeric`, `python` (your own function), and
`llm_judge` (a model scores the output against a rubric). Any grader can be negated for "must not"
checks and weighted in the task score.

Suite-level graders apply to every task, before each task's own graders.

## Scoring

1. A **run** passes when every grader passes. Its score is the weighted mean of the grader scores.
2. A **task** passes when at least `task_pass_rate` of its runs pass.
3. The **suite** passes when at least `fail_under` of its tasks pass.

Task statuses are `pass`, `FAIL`, `FLAKY` (some runs passed, but too few), and `ERROR` (the target
or a grader raised an error).

## Repeats and flakiness

Model output isn't deterministic. Set `repeat` (or pass `-n 10`) to run each task several times.
evalkit reports each task's pass rate across its runs and counts a task as flaky when its runs
disagree. This separates a task that's broken from one that's unreliable.

## The response cache

evalkit stores model responses in a SQLite file (`.evalkit/cache.sqlite` by default). The key is
a hash of the provider identity (provider, model, and settings, never secrets), the prompt, the
system prompt, the seed, and the repeat index. A rerun with unchanged prompts makes no API calls,
so iterating on graders is free. `command` and `http` targets aren't cached by default, because
your app changes between runs. Pass `--no-cache` to bypass the cache for one run.

## Baselines and the regression gate

`evalkit run -o results.json` writes everything about a run. `evalkit compare base.json head.json`
diffs two such files and fails when the pass rate or the mean score drops by more than
`--threshold`, or, with `--strict`, when any single task goes from pass to fail. Save a baseline on
your main branch and compare every pull request against it.

## Outputs

One run can write a terminal table, the full results JSON, JUnit XML for your CI's test report
view, a GitHub-flavored Markdown summary, and a shields.io endpoint badge.
