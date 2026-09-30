# Suite file reference

A suite is a YAML (or JSON) file. Unknown keys are errors, so typos fail loudly. Run
`evalkit validate evals.yaml` to check a file without running it, and `evalkit schema` for a JSON
Schema your editor can use. The full schema is on the [Suite JSON Schema](schema.md) page.

```yaml
version: 1                      # optional, the only version is 1
name: support-bot               # required
description: Optional text shown in reports.

target: {provider: openai, model: gpt-4o-mini}   # required, see "Providers"
judge: {provider: openai, model: gpt-4o-mini}    # default judge for llm_judge graders

system: You are a helpful support agent.         # system prompt for the target
prompt: "Customer says: {{message}}"             # template; omit it to send each task's input as-is

graders:                        # applied to every task, before each task's own graders
  - type: contains
    value: ["Thanks"]

tasks:                          # a list, or a path to a .yaml, .json, or .jsonl file
  - id: refund                  # defaults to task-1, task-2, ...
    vars: {message: "I want a refund"}
    input: null                 # string prompt, or any value when you use `prompt`
    expected: Billing > Refunds # default value for exact, contains, and numeric
    tags: [billing]             # select with `evalkit run -t billing`
    metadata: {owner: payments} # free-form, passed to python graders
    graders:
      - type: regex
        pattern: 'Billing\s*>\s*Refunds'

settings:
  concurrency: 4                # parallel requests
  repeat: 1                     # runs per task, for flakiness stats
  retries: 2                    # retries on timeouts, 429, and 5xx
  retry_backoff: 0.5            # seconds, doubles per attempt
  seed: 0                       # passed to providers that accept a seed
  cache: true                   # cache model responses in SQLite
  cache_path: .evalkit/cache.sqlite   # relative to the directory you run evalkit from
  fail_under: 1.0               # minimum share of passing tasks for exit code 0
  task_pass_rate: 1.0           # share of a task's repeats that must pass
```

## Templates

Prompts, grader values, regex patterns, rubrics, and `http` bodies accept `{{ name }}`
placeholders. The variables are `input`, `expected`, `id`, `metadata`, `vars`, and each key of
`vars` (and of `input`, when it's a mapping) at the top level. Dotted paths such as
`{{ vars.city }}` and `{{ items.0 }}` walk into nested values. A value that is exactly one
placeholder keeps its type, so `value: "{{ expected }}"` can resolve to a number.

Provider settings in `target` and `judge` also expand environment variables: `${VAR}` or
`${VAR:-default}`. Task data is never expanded.

## Providers

Every provider accepts `timeout` (seconds, default 60), `cache` (override the default), and
`pricing: {input_per_mtok, output_per_mtok}` in USD per million tokens. evalkit ships no price
table, so cost is reported only when you set prices.

| Provider | Key fields | Cached by default |
| --- | --- | --- |
| `openai` | `model`, `base_url` (default `https://api.openai.com/v1`), `api_key_env` (default `OPENAI_API_KEY`, `null` for none), `temperature`, `max_tokens`, `headers`, `params` | Yes |
| `anthropic` | `model`, `base_url`, `api_key_env` (default `ANTHROPIC_API_KEY`), `anthropic_version`, `temperature`, `max_tokens` (default 1024), `headers`, `params` | Yes |
| `command` | `command` (string or list), `cwd`, `env`. The prompt goes to stdin unless an argument contains `{{prompt}}`. stdout is the output. `EVALKIT_SEED`, `EVALKIT_REPEAT`, and `EVALKIT_SYSTEM` are set. | No |
| `http` | `url`, `method` (`POST`, `PUT`, or `GET`), `headers`, `body` (JSON template, default `{"input": "{{prompt}}"}`), `output_path` (dotted path into the response, such as `data.answer`) | No |
| `mock` | `responses` (list of `{match: regex, output, flaky}`), `default` (echoes the prompt if unset), `latency_ms`, `flaky`, `flaky_output`, `fail_times` | Yes |

The `openai` provider works with any server that speaks the chat completions API, including
gateways such as LiteLLM and OpenRouter and local servers such as vLLM, llama.cpp, and Ollama.
Set `base_url` and, for servers without auth, `api_key_env: null`.

`params` merges extra fields into the request body, for example `params: {top_p: 0.9}`.

## Scoring

Each grader returns pass or fail, a score from 0 to 1, and a reason. A run passes when every
grader passes. Its score is the weighted mean of the grader scores. A task passes when at least
`task_pass_rate` of its runs pass. The suite passes when at least `fail_under` of its tasks pass.

Task statuses in reports are `pass`, `FAIL`, `FLAKY` (some runs passed, too few to pass the task),
and `ERROR` (the target or a grader raised an error).

## Graders

Every grader accepts `name` (label in reports), `negate: true` (invert the verdict, for "must not"
checks), and `weight` (default 1, used in the task score).

| Type | Passes when | Options |
| --- | --- | --- |
| `exact` | The output equals `value`. | `value` (defaults to `expected`), `ignore_case`, `strip` (default true) |
| `contains` | The output contains `value`, or each item of a list. | `value`, `mode: all` or `any`, `ignore_case`. Score is the share of items found. |
| `regex` | `pattern` matches anywhere in the output. | `pattern`, `ignore_case`, `fullmatch` (match the whole stripped output) |
| `json_schema` | The output is JSON that validates against the schema. | `schema` (inline) or `schema_file` (JSON or YAML, relative to the suite), `extract` (default true: find JSON in code fences or prose) |
| `numeric` | A number in the output is within tolerance of `value`. | `value` (defaults to `expected`), `abs_tol`, `rel_tol`, `pick: last` or `first`. Commas such as `1,250.50` are handled. |
| `python` | Your function says so. | `function` (`checks.py:name` relative to the suite, or `package.module:name`), `args` (keyword arguments) |
| `llm_judge` | A judge model scores the output at or above `min_score`. | `rubric` (templated), `provider` (defaults to the suite `judge`), `scale` (default 5), `min_score` (default `scale - 1`) |

### Python graders

A python grader receives the output and a context dict with `input`, `expected`, `vars`, `id`,
`metadata`, `prompt`, `repeat`, and `seed`. It can be sync or async and returns one of:

```python
def within_length(output, context, max_words=40):
    words = len(output.split())
    return {
        "pass": words <= max_words,
        "score": min(1.0, max_words / max(words, 1)),
        "reason": f"{words} words (max {max_words})",
    }


# Also valid: True / False, a score in [0, 1] (passes at 0.5), or (passed, "reason").
```

### LLM-as-judge

The judge sees the rubric, the task input, the task's `expected` value as a reference when there
is one, and the output. It replies with `{"score": <1..scale>, "reason": "..."}`. evalkit
normalizes the score to 0 to 1 and passes the grade at `min_score`. Judge calls go through the same
retries and cache as the target. A reply without a readable score fails the grade and shows the raw
reply in the reason.

```yaml
judge:
  provider: anthropic       # reads ANTHROPIC_API_KEY
  model: ${JUDGE_MODEL}
graders:
  - type: llm_judge
    name: tone
    rubric: The reply is polite, acknowledges the customer, and gives a concrete next step.
    min_score: 4
```
