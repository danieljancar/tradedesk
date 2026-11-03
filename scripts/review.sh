#!/usr/bin/env bash
# Runs /review headless. Point cron or launchd at this file once a week.
set -uo pipefail

cd "$(dirname "$0")/.."
mkdir -p data/logs
log="data/logs/$(date +%Y-%m-%d).log"
echo "=== $(date '+%F %T') weekly review" >>"$log"

claude -p "/review" --permission-mode dontAsk --allowedTools \
  "Bash(uv run desk stats)" "Bash(uv run desk journal:*)" \
  "Read" "Write" >>"$log" 2>&1
