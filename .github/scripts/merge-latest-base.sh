#!/usr/bin/env bash
set -euo pipefail

if [ "${GITHUB_EVENT_NAME:-}" != "pull_request" ]; then
  exit 0
fi

BASE_REF="${GITHUB_BASE_REF:?GITHUB_BASE_REF is required for pull_request jobs}"

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git fetch --no-tags origin "$BASE_REF"

if git merge-base --is-ancestor "origin/${BASE_REF}" HEAD; then
  echo "HEAD already contains origin/${BASE_REF}"
  exit 0
fi

if git merge --no-edit "origin/${BASE_REF}"; then
  echo "Merged origin/${BASE_REF} into this PR for CI"
  exit 0
fi

echo "::error::Could not merge origin/${BASE_REF} into this PR. Rebase onto latest ${BASE_REF} and push."
git merge --abort || true
exit 1
