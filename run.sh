#!/bin/bash
set -euo pipefail

cd /opt/blog_access
source venv/bin/activate

cmd="${1:-}"
if [ -z "$cmd" ]; then
  echo "用法: ./run.sh [visit|report|proxy-check] [args...]"
  exit 1
fi
shift || true

lock_file="/tmp/blog_access_${cmd}.lock"
exec 9>"$lock_file"
if ! flock -n 9; then
  echo "[$(date '+%F %T')] $cmd 已在运行，跳过本次执行"
  exit 0
fi

xvfb-run -a python blog_visit_per_site_v2.py "$cmd" "$@"
