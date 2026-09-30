# FAQ

## Do I need an API key to try evalkit?

No. `evalkit init` writes a suite that uses the built-in `mock` provider, and every example except
`examples/openai-compatible` runs offline. You need a key only when your target or judge is a
hosted model.

## Why is the PyPI package called `sic-evalkit`?

The name `evalkit` was already taken on PyPI. Install `sic-evalkit`, then run the `evalkit` command
and `import evalkit` as usual.

## Which models can I test?

Any model behind the OpenAI chat completions API or the Anthropic Messages API. That includes
OpenAI, Anthropic, gateways such as LiteLLM and OpenRouter, and local servers such as vLLM,
llama.cpp, and Ollama. Set `base_url`, and set `api_key_env: null` for servers without auth.

## Can I test my app instead of a model?

Yes, and you should. A `command` target runs your program with the prompt on stdin. An `http`
target posts a templated JSON body to your endpoint and reads the answer with `output_path`. Your
graders then check what your users actually see.

## How do I deal with non-deterministic output?

Set `repeat` (or pass `-n`) to run each task several times, and set `task_pass_rate` to the share
of runs that must pass. evalkit marks tasks whose runs disagree as flaky, so you can tell an
unreliable task from a broken one. Prefer graders that check meaning over exact wording, such as
`contains`, `regex`, `json_schema`, or `llm_judge`.

## Does evalkit call the API again when I rerun a suite?

Not for model targets with unchanged prompts. Responses are cached in `.evalkit/cache.sqlite`.
Pass `--no-cache` to measure the live model, or run `evalkit cache clear`.

## How much does a run cost?

evalkit reports token counts for every run. It doesn't ship a price table, because prices change.
Set `pricing: {input_per_mtok, output_per_mtok}` on a provider to get cost in the report.

## How do I fail a pull request when quality drops?

Save `results.json` from a run on `main` and pass it as the baseline:
`evalkit run evals.yaml --baseline base.json --threshold 0.05`. See [CI integration](ci.md).

## Can a `python` grader import my own packages?

With the pip install, yes: the grader runs in the same environment as evalkit. The standalone
executables bundle their own Python, so a grader can import only the standard library modules and
dependencies they include. Use the pip install if your graders need more.

## How do I verify a downloaded executable or the image?

Each release carries `SHA256SUMS`, SPDX SBOMs, and build provenance attestations. Run
`gh attestation verify evalkit-linux-x64 -R superintelligenceco/evalkit` for a file, or
`gh attestation verify oci://ghcr.io/superintelligenceco/evalkit:<version> -R superintelligenceco/evalkit`
for the image. The image is also signed with cosign.

## Is my data sent anywhere?

Only to the targets and judges you configure. evalkit has no telemetry.
