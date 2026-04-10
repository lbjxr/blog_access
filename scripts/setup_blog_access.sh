#!/bin/bash
set -Eeuo pipefail

export VISUAL="${VISUAL:-vim}"
export EDITOR="${EDITOR:-vim}"
export DEBIAN_FRONTEND=noninteractive

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/opt/blog_access}"
WORK_DIR="$REPO_ROOT"
VENV_DIR="$INSTALL_DIR/venv"
RUN_SCRIPT="$INSTALL_DIR/run.sh"
SECRETS_FILE="$INSTALL_DIR/secrets.json"
CRON_VISIT='*/40 * * * * cd /opt/blog_access && ./run.sh visit >> ./cron_visit.log 2>&1'
CRON_REPORT='30 9 * * * cd /opt/blog_access && ./run.sh report >> ./cron_report.log 2>&1'
REQUIRED_FILES=("blog_visit_per_site_v2.py" "requirements.txt" "run.sh" "proxy_utils.py" "ip_proxy_check.py")
TEMPLATE_REQUIRED_FILES=("config.example.json")
OPTIONAL_FILES=("README.md" "install.sh" "setup_blog_access.sh" ".gitignore" "secrets.example.json")
GITHUB_REPO_DEFAULT="${BLOG_ACCESS_REPO:-https://github.com/lbjxr/blog_access.git}"
GITHUB_REF_DEFAULT="${BLOG_ACCESS_REF:-main}"
GITHUB_MODE="${BLOG_ACCESS_SOURCE_MODE:-auto}"
CHECK_ONLY="${BLOG_ACCESS_CHECK_ONLY:-0}"
TMP_SOURCE_DIR=""

GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
BLUE='\033[34m'
BOLD='\033[1m'
RESET='\033[0m'

log() { echo -e "${GREEN}[$(date '+%F %T')] $*${RESET}"; }
warn() { echo -e "${YELLOW}[WARN] $*${RESET}"; }
err() { echo -e "${RED}[ERR] $*${RESET}" >&2; }
step() { echo -e "\n${BOLD}${BLUE}==> $*${RESET}"; }

cleanup() {
  if [[ -n "$TMP_SOURCE_DIR" && -d "$TMP_SOURCE_DIR" ]]; then
    rm -rf "$TMP_SOURCE_DIR"
  fi
}
trap cleanup EXIT
trap 'err "脚本在第 $LINENO 行失败，请检查上面的错误信息。"' ERR

require_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    err "请使用 root 运行：sudo bash $0"
    exit 1
  fi
}

command_exists() { command -v "$1" >/dev/null 2>&1; }

ensure_cmd() {
  local cmd="$1"
  local pkg="${2:-$1}"
  if command_exists "$cmd"; then
    return 0
  fi
  warn "缺少命令 $cmd，尝试安装软件包 $pkg"
  apt_install "$pkg"
  command_exists "$cmd"
}

apt_update_once() {
  if [[ -z "${APT_UPDATED_ONCE:-}" ]]; then
    step "刷新软件包索引"
    apt-get update -y
    APT_UPDATED_ONCE=1
  fi
}

apt_install() {
  if [[ "$CHECK_ONLY" == "1" ]]; then
    warn "CHECK_ONLY=1，跳过安装软件包：$*"
    return 0
  fi
  apt_update_once
  local pkgs=("$@")
  log "安装软件包：${pkgs[*]}"
  apt-get install -y --no-install-recommends "${pkgs[@]}"
}

check_base_env() {
  step "基础环境检查"
  if ! command_exists apt-get; then
    err "当前系统没有 apt-get，脚本暂只支持 Debian/Ubuntu 系。"
    exit 1
  fi

  local missing=()
  for cmd in bash sed awk grep flock python3; do
    command_exists "$cmd" || missing+=("$cmd")
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    warn "缺少基础命令：${missing[*]}，将尝试补齐。"
  fi

  ensure_cmd git git || true
  ensure_cmd curl curl || true
  ensure_cmd wget wget || true
  ensure_cmd flock util-linux || true
  ensure_cmd xauth xauth || true
  ensure_cmd xvfb xvfb || true
  ensure_cmd cron cron || true
  ensure_cmd python3 python3
  ensure_cmd pip3 python3-pip || true

  local py_ver
  py_ver="$(python3 - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
  log "检测到 Python 版本：$py_ver"
  apt_install "python${py_ver}-venv" python3-venv python3-pip ca-certificates
}

has_local_source() {
  local base="$1"
  local file
  for file in "${REQUIRED_FILES[@]}"; do
    [[ -f "$base/$file" ]] || return 1
  done
  for file in "${TEMPLATE_REQUIRED_FILES[@]}"; do
    [[ -f "$base/$file" || -f "$base/${file%.example.json}.json" ]] || return 1
  done
  return 0
}

fetch_source_from_github() {
  local repo_url="$1"
  local ref="$2"

  if [[ -z "$repo_url" ]]; then
    err "未提供 GitHub 仓库地址。请设置 BLOG_ACCESS_REPO，例如：BLOG_ACCESS_REPO=https://github.com/owner/repo.git"
    exit 1
  fi

  TMP_SOURCE_DIR="$(mktemp -d /tmp/blog_access_src.XXXXXX)"
  step "从 GitHub 获取安装源"
  log "仓库：$repo_url"
  log "分支/标签：$ref"

  if command_exists git; then
    if git clone --depth 1 --branch "$ref" "$repo_url" "$TMP_SOURCE_DIR"; then
      WORK_DIR="$TMP_SOURCE_DIR"
      return 0
    fi
    warn "git clone 失败，尝试走 tarball 下载。"
  fi

  local archive_url
  archive_url="${repo_url%.git}/archive/refs/heads/${ref}.tar.gz"
  if command_exists curl; then
    if curl -fsSL "$archive_url" | tar -xz -C "$TMP_SOURCE_DIR" --strip-components=1; then
      WORK_DIR="$TMP_SOURCE_DIR"
      return 0
    fi
  fi
  if command_exists wget; then
    if wget -qO- "$archive_url" | tar -xz -C "$TMP_SOURCE_DIR" --strip-components=1; then
      WORK_DIR="$TMP_SOURCE_DIR"
      return 0
    fi
  fi

  err "无法从 GitHub 获取源码。请检查 BLOG_ACCESS_REPO / BLOG_ACCESS_REF 是否正确，或将脚本与项目文件放在同一目录（或 /opt/blog_access）后重试。"
  exit 1
}

prepare_source() {
  step "检查安装源"

  local candidates=(
    "$WORK_DIR"
    "$WORK_DIR/blog_access"
    "$PWD"
    "$PWD/blog_access"
    "$INSTALL_DIR"
  )
  local candidate

  if [[ "$GITHUB_MODE" == "github" ]]; then
    fetch_source_from_github "$GITHUB_REPO_DEFAULT" "$GITHUB_REF_DEFAULT"
  else
    for candidate in "${candidates[@]}"; do
      if has_local_source "$candidate"; then
        WORK_DIR="$candidate"
        log "检测到本地完整安装源：$WORK_DIR"
        break
      fi
    done

    if ! has_local_source "$WORK_DIR"; then
      warn "本地未发现完整安装源。"
      if [[ -n "$GITHUB_REPO_DEFAULT" ]]; then
        warn "切换到 GitHub 获取模式。"
        fetch_source_from_github "$GITHUB_REPO_DEFAULT" "$GITHUB_REF_DEFAULT"
      else
        err "当前目录、脚本目录及 $INSTALL_DIR 都未发现完整安装源，且自动从默认仓库拉取也不可用。"
        err "如需覆盖默认仓库，可手动设置：BLOG_ACCESS_REPO=https://github.com/owner/repo.git"
        exit 1
      fi
    fi
  fi

  local file
  for file in "${REQUIRED_FILES[@]}"; do
    [[ -f "$WORK_DIR/$file" ]] || { err "安装源仍缺少必要文件：$file"; exit 1; }
  done
  for file in "${TEMPLATE_REQUIRED_FILES[@]}"; do
    [[ -f "$WORK_DIR/$file" || -f "$WORK_DIR/${file%.example.json}.json" ]] || { err "安装源仍缺少配置模板：$file"; exit 1; }
  done
}

backup_existing_install() {
  step "检查并备份现有安装"
  mkdir -p "$INSTALL_DIR"

  if [[ -f "$INSTALL_DIR/config.json" ]]; then
    cp -a "$INSTALL_DIR/config.json" "$INSTALL_DIR/config.json.bak.$(date +%s)"
    log "已备份现有 config.json"
  fi
  if [[ -f "$INSTALL_DIR/run.sh" ]]; then
    cp -a "$INSTALL_DIR/run.sh" "$INSTALL_DIR/run.sh.bak.$(date +%s)"
    log "已备份现有 run.sh"
  fi
  if [[ -f "$SECRETS_FILE" ]]; then
    log "检测到现有 secrets.json，将保留原文件，不覆盖。"
  fi
}

sync_project_files() {
  step "同步项目文件到安装目录"

  if [[ "$WORK_DIR" == "$INSTALL_DIR" ]]; then
    log "安装源与目标目录相同，跳过文件复制，仅执行环境补齐与校验。"
    chmod +x "$INSTALL_DIR/run.sh"
  else
    local file
    for file in "${REQUIRED_FILES[@]}"; do
      install -m 0644 "$WORK_DIR/$file" "$INSTALL_DIR/$file"
    done
    for file in "${OPTIONAL_FILES[@]}"; do
      [[ -f "$WORK_DIR/$file" ]] && install -m 0644 "$WORK_DIR/$file" "$INSTALL_DIR/$file"
    done
    mkdir -p "$INSTALL_DIR/scripts"
    [[ -f "$WORK_DIR/scripts/setup_blog_access.sh" ]] && install -m 0755 "$WORK_DIR/scripts/setup_blog_access.sh" "$INSTALL_DIR/scripts/setup_blog_access.sh"
    chmod +x "$INSTALL_DIR/run.sh" "$INSTALL_DIR/setup_blog_access.sh" "$INSTALL_DIR/install.sh"
  fi

  if [[ ! -f "$INSTALL_DIR/config.json" ]]; then
    if [[ -f "$WORK_DIR/config.json" ]]; then
      install -m 0644 "$WORK_DIR/config.json" "$INSTALL_DIR/config.json"
      log "已初始化 config.json"
    elif [[ -f "$WORK_DIR/config.example.json" ]]; then
      install -m 0644 "$WORK_DIR/config.example.json" "$INSTALL_DIR/config.json"
      log "已根据模板初始化 config.json"
    else
      err "未找到 config.json 或 config.example.json，无法初始化配置。"
      exit 1
    fi
  fi

  if [[ ! -f "$SECRETS_FILE" ]]; then
    if [[ -f "$WORK_DIR/secrets.json" ]]; then
      install -m 0600 "$WORK_DIR/secrets.json" "$SECRETS_FILE"
      log "已初始化 secrets.json"
    elif [[ -f "$WORK_DIR/secrets.example.json" ]]; then
      install -m 0600 "$WORK_DIR/secrets.example.json" "$SECRETS_FILE"
      log "已根据模板初始化 secrets.json"
    else
      cat > "$SECRETS_FILE" <<'EOF'
{
  "telegram": {
    "default_token": "YOUR_BOT_TOKEN",
    "default_chat": "YOUR_CHAT_ID"
  }
}
EOF
      chmod 600 "$SECRETS_FILE"
      warn "已创建 secrets.json 模板，请在使用前填写 Telegram 信息。"
    fi
  fi
}

setup_python_env() {
  step "准备 Python 虚拟环境"
  if [[ "$CHECK_ONLY" == "1" ]]; then
    warn "CHECK_ONLY=1，跳过 venv/依赖安装。"
    return 0
  fi

  if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
    log "已创建虚拟环境：$VENV_DIR"
  else
    log "虚拟环境已存在，沿用：$VENV_DIR"
  fi

  # shellcheck disable=SC1090
  source "$VENV_DIR/bin/activate"

  python -m pip install --upgrade pip setuptools wheel
  python -m pip install -r "$INSTALL_DIR/requirements.txt"

  step "安装 Playwright 浏览器及依赖"
  if command_exists playwright; then
    if ! playwright install-deps; then
      warn "playwright install-deps 失败，尝试手动安装常见依赖。"
      apt_install libasound2 libatk-bridge2.0-0 libatk1.0-0 libcups2 libdrm2 libgbm1 \
        libgtk-3-0 libnspr4 libnss3 libxcomposite1 libxdamage1 libxfixes3 libxkbcommon0 \
        libxrandr2 fonts-noto-color-emoji fonts-liberation
    fi
  else
    warn "未找到 playwright 命令，直接尝试 Python 模块安装浏览器。"
  fi

  if ! python -m playwright install chromium; then
    warn "首次安装 Chromium 失败，重试一次。"
    python -m playwright install chromium
  fi

  deactivate
}

ensure_services() {
  step "确保 cron 服务可用"
  if [[ "$CHECK_ONLY" == "1" ]]; then
    warn "CHECK_ONLY=1，跳过 cron 服务重启。"
    return 0
  fi
  if command_exists systemctl; then
    systemctl enable cron >/dev/null 2>&1 || true
    systemctl restart cron || true
  fi
  service cron restart >/dev/null 2>&1 || true
}

install_cron_jobs() {
  step "配置定时任务"
  if [[ "$CHECK_ONLY" == "1" ]]; then
    warn "CHECK_ONLY=1，跳过 crontab 写入。"
    return 0
  fi
  local tmpcron
  tmpcron="$(mktemp)"
  crontab -l 2>/dev/null | grep -v '/opt/blog_access && ./run.sh visit' | grep -v '/opt/blog_access && ./run.sh report' > "$tmpcron" || true
  {
    cat "$tmpcron"
    echo "$CRON_VISIT"
    echo "$CRON_REPORT"
  } | crontab -
  rm -f "$tmpcron"
  log "已安装/更新 blog_access 定时任务"
}

post_checks() {
  step "安装后自检"
  [[ -x "$RUN_SCRIPT" ]] || { err "run.sh 不可执行"; exit 1; }
  [[ -f "$INSTALL_DIR/blog_visit_per_site_v2.py" ]] || { err "主脚本缺失"; exit 1; }
  [[ -f "$SECRETS_FILE" ]] || { err "secrets.json 缺失"; exit 1; }

  if [[ "$CHECK_ONLY" == "1" ]]; then
    log "CHECK_ONLY=1，自检到核心文件存在，跳过 Python 编译校验。"
    return 0
  fi

  # shellcheck disable=SC1090
  source "$VENV_DIR/bin/activate"
  python -m py_compile "$INSTALL_DIR/blog_visit_per_site_v2.py" "$INSTALL_DIR/proxy_utils.py" "$INSTALL_DIR/ip_proxy_check.py"
  deactivate

  log "自检通过：脚本可编译，核心文件齐全。"
}

show_summary() {
  step "安装完成"
  cat <<EOF
安装目录: $INSTALL_DIR
虚拟环境: $VENV_DIR
运行命令:
  cd $INSTALL_DIR && ./run.sh visit
  cd $INSTALL_DIR && ./run.sh report
  cd $INSTALL_DIR && ./run.sh proxy-check 3

建议检查:
  1. 编辑 $SECRETS_FILE 填入 Telegram bot 信息
  2. 编辑 $INSTALL_DIR/config.json 调整站点、代理、分页等参数
  3. 查看 visit 日志: tail -f $INSTALL_DIR/cron_visit.log
  4. 查看 report 日志: tail -f $INSTALL_DIR/cron_report.log
  5. 查看运行摘要: tail -f $INSTALL_DIR/run_history.jsonl
  6. 查看代理检测历史: tail -f $INSTALL_DIR/proxy_check_history.jsonl

当前定时任务:
  $CRON_VISIT
  $CRON_REPORT

GitHub 扩展说明:
  - 可通过环境变量 BLOG_ACCESS_REPO / BLOG_ACCESS_REF 指定仓库和分支
  - 当当前目录缺少完整安装源时，如已设置 BLOG_ACCESS_REPO，脚本会自动尝试从 GitHub 拉取源码
  - 可先做预检查而不实际安装：BLOG_ACCESS_CHECK_ONLY=1 bash setup_blog_access.sh
  - 也可强制使用 GitHub 源：BLOG_ACCESS_SOURCE_MODE=github BLOG_ACCESS_REPO=https://github.com/owner/repo.git bash setup_blog_access.sh
EOF
}

main() {
  echo -e "${BOLD}blog_access 一键初始化脚本${RESET}"
  echo -e "- 带基础环境检查"
  echo -e "- 带 Playwright / Python 安装冗余处理"
  echo -e "- 兼容本地源码或 GitHub 拉取安装"
  echo -e "- 保留现有 secrets / 统计 / 日志，不做破坏性覆盖"
  if [[ "$CHECK_ONLY" == "1" ]]; then
    echo -e "- 当前模式：CHECK_ONLY（只检查，不执行安装/修改）"
  fi

  require_root
  check_base_env
  prepare_source
  backup_existing_install
  sync_project_files
  setup_python_env
  install_cron_jobs
  ensure_services
  post_checks
  show_summary
}

main "$@"
