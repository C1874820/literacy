#!/bin/bash
set -a
. /mnt/d/rex-识字系统/.env
set +a
exec /usr/bin/python3 /mnt/d/rex-识字系统/scripts/auto_sync.py
