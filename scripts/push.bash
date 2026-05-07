#!/usr/bin/env bash
# =========================
# Quick git push script for lnut-bot
# =========================

set -e

cd "$(dirname "$0")/.." || exit 1

if [ -z "$(git status --porcelain)" ]; then
    echo "[PUSH] Nothing to commit — working tree clean."
    exit 0
fi

COMMIT_MSG="${1:-auto: update $(date '+%Y-%m-%d %H:%M')}"

echo "[PUSH] Adding all changes..."
git add -A

echo "[PUSH] Committing..."
git commit -m "$COMMIT_MSG"

echo "[PUSH] Pushing to origin/main..."
git push origin main

echo "[PUSH] Done."
