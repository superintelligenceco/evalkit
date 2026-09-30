# 0002. Cache model responses in SQLite

Status: Accepted

## Context

Running a suite against a paid model costs money and time. Most reruns change a grader, a
threshold, or a report option, not the prompt, so the model responses are the same. Teams also run
the same suite on `main` and on every pull request.

## Decision

evalkit stores every model response in a SQLite file, `.evalkit/cache.sqlite` by default. The key
is a SHA-256 hash of the provider identity (provider, model, and settings, but never secrets), the
prompt, the system prompt, the seed, and the repeat index. Including the repeat index keeps the
runs of a repeated task distinct, so flakiness statistics stay honest. `command` and `http`
targets aren't cached by default, because they test your changing app. `--no-cache` and
`cache: false` turn it off.

## Consequences

- A rerun with unchanged prompts makes no API calls, so iterating on graders is free.
- SQLite ships with Python, needs no server, and is a single file you can keep between CI jobs
  with `actions/cache`.
- A cached response hides a provider-side model update behind the same model name. Run with
  `--no-cache` when you want to measure the live model.
