#!/bin/bash
set -Eeuo pipefail

# GitHub 一键安装入口脚本。
# 默认直接安装当前仓库 main 分支。

DEFAULT_REPO="https://github.com/lbjxr/blog_access.git"
DEFAULT_REF="main"
TMP_DIR="$(mktemp -d /tmp/blog_access_install.XXXXXX)"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT
trap 'echo "[ERR] 安装入口执行失败，请检查上方日志。" >&2' ERR


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
