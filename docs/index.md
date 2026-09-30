# evalkit

**Evals as code for LLM apps and agents.** You write tasks and graders in a YAML suite, run them
against a model or your own app, and fail the build when quality regresses.

![evalkit running the support-bot example suite](assets/demo.gif)

evalkit sends each task to a target, grades the answers, and gives you a results table, JSON and
JUnit output, a regression diff against a saved baseline, and a badge. It runs the same on your
laptop and in GitHub Actions.

## Install

=== "pip"

    ```sh
    pip install sic-evalkit
    ```

    The distribution is named `sic-evalkit`. The command and the Python package are both `evalkit`.

=== "Standalone executable"

    ```sh
    curl -fsSL https://raw.githubusercontent.com/superintelligenceco/evalkit/main/install.sh | sh
    ```

    The installer downloads the executable for your OS and CPU from the latest
    [GitHub Release](https://github.com/superintelligenceco/evalkit/releases), checks it against
    `SHA256SUMS`, and puts it in `~/.local/bin`.

=== "Container"

    ```sh
    docker run --rm ghcr.io/superintelligenceco/evalkit run evals.yaml
    ```

    The image's working directory holds a starter suite, so this command runs offline.

## Where to go next

- [Quickstart](quickstart.md): run your first suite in a minute, offline.
- [Concepts](concepts.md): suites, targets, graders, scoring, repeats, the cache, and baselines.
- [CI integration](ci.md): the GitHub Action and gating pull requests on regressions.
- [Command-line reference](reference/cli.md) and [suite file reference](reference/suite.md).
- [Architecture](architecture.md) and the [decision records](adr/index.md).
- [FAQ](faq.md).
