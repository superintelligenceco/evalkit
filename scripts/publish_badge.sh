#!/usr/bin/env bash
# Publish a shields.io endpoint badge JSON to the `badges` branch.
#
# Usage: scripts/publish_badge.sh NAME FILE
#
# Writes FILE as NAME.json on the orphan `badges` branch, so the README can point
# https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/<repo>/badges/NAME.json
# at it. Needs GH_TOKEN (contents: write) and GITHUB_REPOSITORY. Retries on push races.
set -euo pipefail

name="$1"
file="$(realpath "$2")"
remote="https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
work="$(mktemp -d)"
cd "$work"
git init -q
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

for attempt in 1 2 3 4 5; do
  if git fetch -q --depth=1 "$remote" badges 2> /dev/null; then
    git checkout -q -B badges FETCH_HEAD
  else
    git checkout -q --orphan badges
    git rm -rfq . 2> /dev/null || true
  fi
  cp "$file" "$name.json"
  git add "$name.json"
  if git diff --cached --quiet; then
    echo "$name.json is unchanged"
    exit 0
  fi
  git commit -q -m "chore(badges): update $name"
  if git push -q "$remote" HEAD:badges; then
    echo "published $name.json"
    exit 0
  fi
  echo "push attempt $attempt failed, retrying"
  sleep $((attempt * 3))
done
exit 1
