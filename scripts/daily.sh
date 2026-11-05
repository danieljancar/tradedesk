#!/usr/bin/env bash
# Runs /daily headless. Point cron or launchd at this file.
set -uo pipefail

cd "$(dirname "$0")/.."
mkdir -p data/logs
log="data/logs/$(date +%Y-%m-%d).log"
echo "=== $(date '+%F %T') daily run" >>"$log"

# A quiet hour needs no agents: the sync still handles fills, stops and trailing.
if [ -z "${FORCE:-}" ] && ! uv run desk gate >>"$log" 2>&1; then
  uv run desk sync >>"$log" 2>&1 || true
  exit 0
fi

claude -p "/daily" --output-format json --permission-mode dontAsk --allowedTools \
  "Bash(uv run desk run:*)" "Bash(uv run desk sync)" "Bash(uv run desk snapshot)" \
  "Bash(uv run desk news)" "Bash(uv run desk book)" "Bash(uv run desk post:*)" \
  "Bash(uv run desk check:*)" "Bash(uv run desk execute)" "Bash(uv run desk status)" \
  "Bash(uv run desk plans:*)" "Bash(uv run desk journal:*)" \
  "Read" "Write" "Agent" "WebSearch" >"data/logs/last-run.json" 2>>"$log"
status=$?
cat data/logs/last-run.json >>"$log"
# one line per run with tokens and the API-equivalent cost, for the usage view
python3 - <<'PY' >>data/logs/usage.jsonl 2>/dev/null || true
import json, os, datetime
r = json.load(open("data/logs/last-run.json"))
u = r.get("usage") or {}
print(json.dumps({
    "ts": datetime.datetime.now().isoformat(timespec="seconds"),
    "config": os.environ.get("DESK_CONFIG", "desk.toml"),
    "input": u.get("input_tokens"), "output": u.get("output_tokens"),
    "cache_read": u.get("cache_read_input_tokens"), "cache_write": u.get("cache_creation_input_tokens"),
    "cost_usd": r.get("total_cost_usd"), "turns": r.get("num_turns"), "seconds": (r.get("duration_ms") or 0) / 1000,
}))
PY

# If the agents stopped half way, finish the mechanical steps so no run is left hanging.
uv run desk run recover >>"$log" 2>&1 || true
uv run desk sync >>"$log" 2>&1 || true
# Core sleeve: propose rebalancing buys and trims; with auto_execute they go out right away.
uv run desk rebalance --propose >>"$log" 2>&1 && uv run desk execute >>"$log" 2>&1 || true
exit $status
