#!/usr/bin/env bash
# Runs /daily headless. Point cron or launchd at this file.
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p data/logs
log="data/logs/$(date +%Y-%m-%d).log"

claude -p "/daily" --permission-mode dontAsk >>"$log" 2>&1 || {
  uv run desk sync >>"$log" 2>&1
  exit 1
}
