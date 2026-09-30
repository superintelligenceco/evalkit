# Security policy

## Supported versions

Security fixes land on the latest minor release.

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |

## Report a vulnerability

Don't open a public issue for a security problem. Report it privately through
[GitHub private vulnerability reporting](https://github.com/superintelligenceco/evalkit/security/advisories/new).

Include the version, the command you ran, and the smallest suite file that reproduces the problem.
You get an acknowledgment within 5 business days. After the fix ships, the advisory is published
with credit to you unless you ask otherwise.

## Trust model

A suite file is code. Treat it like a Makefile or a CI workflow:

- A `command` target runs the program you name with your environment.
- A `python` grader imports and runs the file or module you name.
- `${VAR}` references in `target` and `judge` read your environment, including API keys.

Only run suites you trust. The `openai` and `anthropic` providers read keys only from the
environment variables you name in `api_key_env` and never write them to disk. The response cache
stores a SHA-256 hash of the request and provider settings, the provider label, and the response
text. Reports include the provider label, which is the URL for `http` targets, so put tokens in
`headers` rather than in the URL.

In scope:

- API keys or other secrets that end up in the cache, results, JUnit, Markdown, or badge output.
- Model output that injects content into a terminal, a job summary, or JUnit XML in a way that
  changes how the report reads.
- A way to make evalkit report a passing run that did not pass.

A grader that gives a wrong verdict is a bug, not a vulnerability. Open a regular issue for it.
