#!/usr/bin/env bash
# Runs /daily headless. Point cron or launchd at this file.
set -uo pipefail

cd "$(dirname "$0")/.."
mkdir -p data/logs
log="data/logs/$(date +%Y-%m-%d).log"
echo "=== $(date '+%F %T') daily run" >>"$log"

claude -p "/daily" --permission-mode dontAsk --allowedTools \
  "Bash(uv run desk run:*)" "Bash(uv run desk sync)" "Bash(uv run desk snapshot)" \
  "Bash(uv run desk news)" "Bash(uv run desk book)" "Bash(uv run desk post:*)" \
  "Bash(uv run desk check:*)" "Bash(uv run desk execute)" "Bash(uv run desk status)" \
  "Bash(uv run desk plans:*)" "Bash(uv run desk journal:*)" \
  "Read" "Write" "Agent" "WebSearch" >>"$log" 2>&1
status=$?

# If the agents stopped half way, finish the mechanical steps so no run is left hanging.
uv run desk run recover >>"$log" 2>&1 || true
uv run desk sync >>"$log" 2>&1 || true
# Core sleeve: propose rebalancing buys and trims; with auto_execute they go out right away.
uv run desk rebalance --propose >>"$log" 2>&1 && uv run desk execute >>"$log" 2>&1 || true
exit $status
