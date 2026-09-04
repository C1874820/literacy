#!/bin/bash
set -a
. /mnt/d/rex/.env
set +a
exec /usr/bin/python3 /mnt/d/rex/scripts/auto_sync.py
