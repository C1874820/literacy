#!/bin/bash
# cron 环境的 PATH 不含 ~/.npm-global/bin，会导致 update_weekly_focus.py 找不到 flowus CLI
export PATH="$HOME/.npm-global/bin:$PATH"
set -a
. /mnt/d/rex/.env
set +a
exec /usr/bin/python3 /mnt/d/rex/scripts/auto_sync.py
