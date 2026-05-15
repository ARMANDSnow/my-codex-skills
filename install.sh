#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_ROOT="${CODEX_HOME:-"$HOME/.codex"}/skills"

SKILLS=(
  "resume-parser-hr"
  "hr-recruit-sop-qa"
)

mkdir -p "$DEST_ROOT"

for skill in "${SKILLS[@]}"; do
  src="$ROOT_DIR/$skill"
  dest="$DEST_ROOT/$skill"

  if [[ ! -d "$src" ]]; then
    echo "Missing skill directory: $src" >&2
    exit 1
  fi

  rm -rf "$dest"
  mkdir -p "$dest"
  rsync -a --delete --exclude ".DS_Store" "$src/" "$dest/"
  echo "Installed $skill -> $dest"
done

echo "Done. Restart Codex to pick up new or updated skills."
