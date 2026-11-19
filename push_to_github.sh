#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
remote_url="https://github.com/Rohibuilds/cleartrace-data-quality.git"
cd "$repo_dir"

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is required. Install it from https://cli.github.com/ and sign in first."
  exit 1
fi
if ! gh auth status --hostname github.com >/dev/null 2>&1; then
  echo "GitHub CLI is not signed in. Run: gh auth login --hostname github.com --git-protocol https --web"
  exit 1
fi

gh auth setup-git

if [ ! -d .git ]; then
  git init -b main
fi

if git remote get-url origin >/dev/null 2>&1; then
  current_remote="$(git remote get-url origin)"
  if [ "$current_remote" != "$remote_url" ]; then
    echo "The origin remote points to a different repository: $current_remote"
    exit 1
  fi
else
  git remote add origin "$remote_url"
fi

git fetch origin main
# Base this upload on the starter README commit while preserving the local files.
git reset --mixed origin/main
git add -A

if git diff --cached --quiet; then
  echo "No local file changes to commit."
else
  git commit -m "Publish complete ClearTrace application and documentation"
fi

git push -u origin main
echo "ClearTrace project pushed to $remote_url"
