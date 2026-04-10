#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "[WARN] 当前目录还不是 git 仓库，先执行 git init 或在真正仓库目录里运行本脚本。"
  echo
  echo "== sensitive file presence =="
  for f in secrets.json .env visit_stats.json cron_visit.log cron_report.log run_history.jsonl proxy_check_history.jsonl venv; do
    if [[ -e "$f" ]]; then
      echo "[WARN] present: $f"
    fi
  done
  exit 0
fi

echo "== git status =="
git status --short || true

echo
echo "== sensitive file presence =="
for f in secrets.json .env visit_stats.json cron_visit.log cron_report.log run_history.jsonl proxy_check_history.jsonl venv; do
  if [[ -e "$f" ]]; then
    echo "[WARN] present: $f"
  fi
done

echo
echo "== ignored check =="
git check-ignore -v secrets.json .env visit_stats.json cron_visit.log cron_report.log run_history.jsonl proxy_check_history.jsonl venv 2>/dev/null || true

echo
echo "== tracked sensitive files =="
git ls-files | grep -E '(^|/)(secrets\.json|\.env|visit_stats\.json|cron_visit\.log|cron_report\.log|run_history\.jsonl|proxy_check_history\.jsonl)$' || true

echo
echo "== grep possible secrets in tracked text files =="
git ls-files | grep -Ev '(^|/)(venv/|__pycache__/)' | while read -r f; do
  grep -nE '(AAG[[:alnum:]_-]{20,}|bot[0-9]{6,}:[[:alnum:]_-]{20,}|https?://[^[:space:]]+:[^@[:space:]]+@|default_token|default_chat)' "$f" && echo "-- $f" || true
done

echo
echo "检查完成：发布前请确认上面没有真实敏感数据被跟踪。"
