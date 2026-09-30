# 0004. Ship standalone executables built with PyInstaller

Status: Accepted

## Context

evalkit's users are often not Python projects. A TypeScript or Go team that wants to gate its
chatbot on evals shouldn't need to manage a Python install and a virtual environment in CI. The
container image helps where Docker is available, but not on macOS laptops or Windows runners.

## Decision

Each release builds a single-file `evalkit` executable with PyInstaller for Linux x64, Linux arm64,
macOS arm64, macOS x64, and Windows x64. The Linux builds run in a Debian bullseye container so
they work on glibc 2.31 and later. Each build runs the starter suite with the new executable before
upload, and `install.sh` downloads the right one and checks it against `SHA256SUMS`.

## Consequences

- You can run evalkit anywhere with one download, no Python needed.
- `python` graders run on the bundled Python 3.12 and can import only what the executable bundles.
  Suites that need other packages should use the pip install.
- The macOS and Windows executables aren't code-signed, so a browser download can trigger
  Gatekeeper or SmartScreen. The installer and `curl` downloads avoid that.
- Each executable is tens of megabytes, much larger than the wheel.
