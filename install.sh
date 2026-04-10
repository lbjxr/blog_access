#!/bin/bash
set -Eeuo pipefail

# 用于未来 GitHub 一键安装的入口脚本。
# 发布到 GitHub 前，请把 DEFAULT_REPO 改成真实仓库地址，
# 这样新机器上只需一条 curl 命令即可完成安装。

DEFAULT_REPO="${BLOG_ACCESS_REPO:-https://github.com/OWNER/REPO.git}"
DEFAULT_REF="${BLOG_ACCESS_REF:-main}"
TMP_DIR="$(mktemp -d /tmp/blog_access_install.XXXXXX)"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT
trap 'echo "[ERR] 安装入口执行失败，请检查上方日志。" >&2' ERR

if [[ "$DEFAULT_REPO" == *"OWNER/REPO"* ]]; then
  echo "[ERR] 当前 install.sh 仍是占位仓库地址。" >&2
  echo "请在发布前把 DEFAULT_REPO 改成真实仓库，或临时这样运行：" >&2
  echo "BLOG_ACCESS_REPO=https://github.com/owner/repo.git curl -fsSL <raw-install-url> | sudo bash" >&2
  exit 1
fi

if command -v git >/dev/null 2>&1; then
  git clone --depth 1 --branch "$DEFAULT_REF" "$DEFAULT_REPO" "$TMP_DIR/repo"
else
  ARCHIVE_URL="${DEFAULT_REPO%.git}/archive/refs/heads/${DEFAULT_REF}.tar.gz"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$ARCHIVE_URL" | tar -xz -C "$TMP_DIR"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- "$ARCHIVE_URL" | tar -xz -C "$TMP_DIR"
  else
    echo "[ERR] 缺少 git/curl/wget，无法获取仓库源码。" >&2
    exit 1
  fi
  REPO_DIR="$(find "$TMP_DIR" -maxdepth 1 -mindepth 1 -type d | head -n1)"
  mv "$REPO_DIR" "$TMP_DIR/repo"
fi

cd "$TMP_DIR/repo"
exec bash ./setup_blog_access.sh "$@"
