#!/usr/bin/env bash
# Plays the README demo: run the support-bot suite, break one reply, and catch the regression.
#
# Record it with asciinema 2 and render it with agg:
#
#   asciinema rec --cols 108 --rows 28 -c scripts/demo.sh demo.cast
#   agg --font-family "JetBrains Mono" --font-size 16 --theme monokai \
#     --idle-time-limit 5 --last-frame-duration 4 demo.cast docs/assets/demo.gif
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cp -r "$repo/examples/support-bot" "$work/"
rm -rf "$work/support-bot/__pycache__"
cd "$work"
export FORCE_COLOR=1

type_cmd() {
  printf '\033[1;32m$\033[0m '
  local s="$1"
  for ((i = 0; i < ${#s}; i++)); do
    printf '%s' "${s:i:1}"
    sleep 0.035
  done
  sleep 0.5
  printf '\n'
  eval "$1" || true
  sleep "${2:-2.5}"
}

clear
type_cmd "evalkit run support-bot/evals.yaml -o base.json" 3.5
type_cmd "sed -i 's/Billing > Refunds/the billing page/' support-bot/bot.py" 0.8
type_cmd "evalkit run support-bot/evals.yaml --baseline base.json" 4
