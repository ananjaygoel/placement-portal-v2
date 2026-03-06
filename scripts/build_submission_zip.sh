#!/usr/bin/env bash
set -euo pipefail

prefix="${1:-placement-portal-v2-main/}"
output="${2:-placement-portal-v2-main.zip}"

if ! command -v git >/dev/null 2>&1; then
  echo "error: git is required to build a code-only submission zip" >&2
  exit 1
fi

git archive --format=zip --prefix="$prefix" -o "$output" HEAD
echo "Wrote $output"
