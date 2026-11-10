#!/usr/bin/env bash
# Writes the daily market brief. Point launchd at this file once a day.
set -uo pipefail

cd "$(dirname "$0")/.."
mkdir -p data/logs data/ticker
log="data/logs/$(date +%Y-%m-%d)-ticker.log"
echo "=== $(date '+%F %T') market brief" >>"$log"

claude -p "/ticker" --output-format json --permission-mode dontAsk --allowedTools \
  "Bash(uv run desk ticker)" "Read" "Write" "WebSearch" >"data/logs/last-ticker.json" 2>>"$log"
status=$?
cat data/logs/last-ticker.json >>"$log"; echo >>"$log"
RUN_OUT=data/logs/last-ticker.json python3 - <<'PY' >>data/logs/usage.jsonl 2>/dev/null || true
import json, os, datetime
r = json.load(open(os.environ["RUN_OUT"]))
u = r.get("usage") or {}
print(json.dumps({
    "ts": datetime.datetime.now().isoformat(timespec="seconds"), "config": "ticker",
    "input": u.get("input_tokens"), "output": u.get("output_tokens"),
    "cache_read": u.get("cache_read_input_tokens"), "cache_write": u.get("cache_creation_input_tokens"),
    "cost_usd": r.get("total_cost_usd"), "turns": r.get("num_turns"), "seconds": (r.get("duration_ms") or 0) / 1000,
}))
PY
exit $status
