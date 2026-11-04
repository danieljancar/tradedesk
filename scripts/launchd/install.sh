#!/usr/bin/env bash
# Installs the Telegram bot and the morning report as launchd jobs for this user.
# Usage: scripts/launchd/install.sh [HH:MM]   (report time, default 07:30)
#        scripts/launchd/install.sh --remove
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
agents="$HOME/Library/LaunchAgents"
domain="gui/$(id -u)"
jobs=(tradedesk.bot tradedesk.report)

if [[ "${1:-}" == "--remove" ]]; then
  for job in "${jobs[@]}"; do
    launchctl bootout "$domain/$job" 2>/dev/null || true
    rm -f "$agents/$job.plist"
  done
  echo "removed ${jobs[*]}"
  exit 0
fi

uv="$(command -v uv)" || { echo "uv not found on PATH" >&2; exit 1; }
time="${1:-07:30}"
hour="$((10#${time%%:*}))"
minute="$((10#${time##*:}))"

mkdir -p "$agents" "$root/data/logs"
for job in "${jobs[@]}"; do
  target="$agents/$job.plist"
  sed -e "s|__UV__|$uv|g" -e "s|__ROOT__|$root|g" -e "s|__PATH__|$(dirname "$uv"):/usr/bin:/bin|g" \
    -e "s|__HOUR__|$hour|g" -e "s|__MINUTE__|$minute|g" "$here/$job.plist" >"$target"
  plutil -lint "$target" >/dev/null
  launchctl bootout "$domain/$job" 2>/dev/null || true
  launchctl bootstrap "$domain" "$target"
done
printf 'bot running, report every day at %02d:%02d, logs in %s\n' "$hour" "$minute" "$root/data/logs"
