# blog_access

一个基于 **Playwright** 的博客访问模拟工具，支持多站点访问、HTTP 认证代理、访问统计、Telegram 日报，以及代理出口检测。

适合用在：
- 自建博客的基础访问模拟
- 多站点定时访问任务
- 需要通过浏览器而不是裸 HTTP 请求进行访问的场景
- 需要结合 HTTP 代理池做访问分流的场景

---

## Features

- **Playwright 浏览器访问**：不是简单 requests，支持更接近真实浏览行为的访问流程
- **多站点访问**：一个配置可管理多个站点
- **HTTP 认证代理支持**：支持 `http://user:pass@host:port` 形式代理
- **代理健康检查 + 回退直连**：代理异常时可自动回退，避免任务完全失败
- **访问统计**：累计访问数、代理访问数、直连访问数、失败数等
- **Telegram 报告**：支持日报发送、dry-run、skip-clear
- **代理出口检测**：可直接检测代理池出口 IP 是否在轮换
- **安装脚本**：支持本地安装、GitHub 拉取安装、curl 一键安装

---

## Quick Start

### 1. 一键安装（推荐）

```bash
curl -fsSL https://raw.githubusercontent.com/lbjxr/blog_access/main/install.sh | sudo bash
```

### 2. 一键预检查（不真正安装）

```bash
curl -fsSL https://raw.githubusercontent.com/lbjxr/blog_access/main/install.sh | sudo env BLOG_ACCESS_CHECK_ONLY=1 bash
```

### 3. 安装后运行

```bash
cd /opt/blog_access
./run.sh visit
./run.sh report
./run.sh proxy-check 3
```

---

## Project Structure

```text
install.sh                     # curl | bash 一键安装入口
setup_blog_access.sh           # 根目录安装入口
scripts/setup_blog_access.sh   # 安装器主体
scripts/github_publish_check.sh# 发布前敏感信息检查
blog_visit_per_site_v2.py      # 主访问脚本
proxy_utils.py                 # 代理解析与健康检查
ip_proxy_check.py              # 代理出口检测
run.sh                         # 运行入口（带互斥锁）
config.example.json            # 配置模板
secrets.example.json           # 密钥模板
```

---

## Installation Modes

### Local Source Install

```bash
sudo bash setup_blog_access.sh
```

### GitHub Source Install

默认仓库已指向：`https://github.com/lbjxr/blog_access.git`

```bash
sudo BLOG_ACCESS_SOURCE_MODE=github \
  BLOG_ACCESS_REF=main \
  bash setup_blog_access.sh
```

如果你要临时改为别的仓库，再额外传：

```bash
sudo BLOG_ACCESS_SOURCE_MODE=github \
  BLOG_ACCESS_REPO=https://github.com/owner/repo.git \
  BLOG_ACCESS_REF=main \
  bash setup_blog_access.sh
```

### Check Only

```bash
sudo BLOG_ACCESS_CHECK_ONLY=1 bash setup_blog_access.sh
```

---

## Usage

进入安装目录后执行：

```bash
cd /opt/blog_access
./run.sh visit
./run.sh report
./run.sh proxy-check
```

### Commands

#### visit
执行博客访问任务。

```bash
./run.sh visit
./run.sh visit server-name
```

#### report
发送统计报告。

```bash
./run.sh report
./run.sh report server-name
```

#### proxy-check
检测代理出口 IP。

```bash
./run.sh proxy-check
./run.sh proxy-check 3
```

---

## Configuration

### `config.json`
主配置文件，保存站点、代理、分页等信息。通过 GitHub/一键安装时，如果仓库中没有真实 `config.json`，安装器会自动根据 `config.example.json` 生成一份。

示例：

```json
{
  "proxy": {
    "enabled": true,
    "url": "http://Default:YOUR_PROXY_PASSWORD@YOUR_PROXY_HOST:YOUR_PROXY_PORT",
    "bypass": "localhost,127.0.0.1",
    "fallback_direct": true,
    "healthcheck": {
      "enabled": true,
      "url": "https://www.gstatic.com/generate_204",
      "timeout": 10,
      "expected_statuses": [200, 204, 301, 302]
    }
  },
  "sites": [
    {
      "url": "https://example.com"
    }
  ],
  "pages": 3,
  "headless": true
}
```

### `secrets.json`
保存 Telegram 相关敏感信息。通过 GitHub/一键安装时，如果仓库中没有真实 `secrets.json`，安装器会自动根据 `secrets.example.json` 生成一份模板。

```json
{
  "telegram": {
    "default_token": "YOUR_BOT_TOKEN",
    "default_chat": "YOUR_CHAT_ID"
  }
}
```

Telegram 配置解析优先级：
1. 站点内 `tg_token` / `tg_chat`
2. 环境变量 `BLOG_ACCESS_TG_TOKEN` / `BLOG_ACCESS_TG_CHAT`
3. `secrets.json`

---

## Site Selectors

支持站点级选择器覆盖：

```json
{
  "url": "https://example.com",
  "selectors": {
    "cards": ["div.recent-post-item", "div.post-block"],
    "title_links": ["a.article-title"],
    "fallback_links": ["div.post-button a.btn", "h2.post-title a"]
  }
}
```

未配置时使用默认选择器。

---

## Statistics

`visit_stats.json` 主要字段：

- `total_visits`
- `successful_visits`
- `failed_visits`
- `proxy_visits`
- `direct_visits`
- `proxy_healthcheck_failures`
- `proxy_launch_failovers`
- `run_count`
- `last_run_articles`
- `last_run_proxy_articles`
- `last_run_direct_articles`

---

## Runtime Files

运行过程中会生成：

- `cron_visit.log`
- `cron_report.log`
- `visit_stats.json`
- `run_history.jsonl`
- `proxy_check_history.jsonl`

这些文件都属于运行态数据，不建议提交到 GitHub。

---

## Report Debug Options

### Dry Run
只预览报告，不真实发送：

```bash
BLOG_ACCESS_DRY_RUN=1 ./run.sh report test
```

### Skip Clear
真实发送报告，但发送后保留统计文件：

```bash
BLOG_ACCESS_SKIP_CLEAR=1 ./run.sh report test
```

---

## Default Cron Example

```cron
*/40 * * * * cd /opt/blog_access && ./run.sh visit >> ./cron_visit.log 2>&1
30 9 * * * cd /opt/blog_access && ./run.sh report >> ./cron_report.log 2>&1
```

---

## Notes

如果你准备二次开发或重新发布：
- 使用 `config.example.json` 和 `secrets.example.json` 作为公开模板
- 使用 `.gitignore` 避免提交日志、状态文件和 secrets
- 使用 `scripts/github_publish_check.sh` 在 push 前做一次检查

---

## License

本仓库当前包含 `LICENSE` 文件，具体以仓库内文件内容为准。
