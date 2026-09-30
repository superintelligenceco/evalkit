# 0003. Release from a version tag, not release-please

Status: Accepted. Replaces the release-please flow used for 0.1.0.

## Context

evalkit 0.1.0 shipped with release-please, which opens a release pull request from Conventional
Commits and creates the tag when you merge it. evalkit then grew a release that builds much more
than a tag and notes: executables on five runners, a multi-arch image, SBOMs, provenance
attestations, cosign signatures, and a PyPI upload. With release-please, the tag comes from a bot
merge in one workflow and the build reacts to it in another, so two workflows share the release
and a failure in either leaves it half done.

## Decision

A single workflow, `release.yml`, runs when you push an annotated `vX.Y.Z` tag. It checks that the
tag matches the version in `pyproject.toml`, builds and smoke-tests every artifact, attests and
signs them, publishes to PyPI, and creates the GitHub Release with the notes from `CHANGELOG.md`.
You update the changelog and the version by hand in a normal pull request.

## Consequences

- One path produces every published file, and the tag names exactly the commit it came from.
- A release is a deliberate act: the maintainer writes the changelog entry.
- Nothing generates the changelog from commit messages, so a missing entry is caught in review,
  not by tooling.
