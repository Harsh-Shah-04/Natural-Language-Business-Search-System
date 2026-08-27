#!/usr/bin/env bash
# Sync backend/ into the Hugging Face Space repo and push.
#
# Requires in the environment (never on the command line, never committed):
#   HF_TOKEN  — Hugging Face token with write scope
#   HF_SPACE  — target space, e.g. "harsh-shah/business-search-backend"
#
# Secrets (MONGODB_URI, LLM_API_KEY, ...) are set in the Space's own secret
# store, not here. This script pushes code only.
set -euo pipefail

: "${HF_TOKEN:?HF_TOKEN is not set}"
: "${HF_SPACE:?HF_SPACE is not set}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

git clone --depth 1 "https://user:${HF_TOKEN}@huggingface.co/spaces/${HF_SPACE}" "$WORK/space"

cd "$WORK/space"
# Replace tracked content wholesale so deletions upstream propagate, but keep
# the Space repo's own git metadata.
find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +

cp "$REPO_ROOT/deploy/hf-space-README.md" README.md
cp "$REPO_ROOT/backend/Dockerfile" Dockerfile
cp "$REPO_ROOT/backend/.dockerignore" .dockerignore
cp "$REPO_ROOT/backend/pyproject.toml" pyproject.toml
cp -r "$REPO_ROOT/backend/app" app
find app -name '__pycache__' -type d -prune -exec rm -rf {} +

git add -A
if git diff --cached --quiet; then
  echo "No changes to push."
  exit 0
fi
git -c user.email="deploy@local" -c user.name="deploy" \
    commit -m "Sync backend from ${REPO_ROOT##*/} @ $(git -C "$REPO_ROOT" rev-parse --short HEAD)"
git push
echo "Pushed to https://huggingface.co/spaces/${HF_SPACE}"
