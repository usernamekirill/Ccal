#!/bin/sh
set -eu
cd /app
python init_db.py
exec python main.py
