#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install uv first: https://docs.astral.sh/uv/"
  exit 1
fi

uv tool install --force --from "$ROOT" regnskap-agent

SKILL_TARGET="${CODEX_HOME:-$HOME/.codex}/skills/fiken-regnskap"
mkdir -p "$(dirname "$SKILL_TARGET")"
rm -rf "$SKILL_TARGET"
cp -R "$ROOT/skills/fiken-regnskap" "$SKILL_TARGET"

echo "Installed regnskap CLI and fiken-regnskap skill."
echo "Next: regnskap setup --token-stdin --auto-company"
