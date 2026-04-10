# blog_access

一个基于 Playwright 的博客访问模拟脚本，支持：
- 多站点自动访问
- 按页翻页、随机点文章、随机滚动和停留
- 访问统计落盘
- Telegram 日报发送
- HTTP 认证代理（浏览器实例级，不影响 VPS 全局网络）
- 代理出口检测

## 适合 GitHub 首发的仓库结构

- `install.sh`：未来给 `curl | bash` 一键安装用的入口
- `setup_blog_access.sh`：根目录安装入口
- `scripts/setup_blog_access.sh`：安装器主体
- `scripts/github_publish_check.sh`：发布前自检敏感信息
- `config.example.json`：公开配置模板
- `secrets.example.json`：公开密钥模板
- `.gitignore`：忽略本地密钥、日志、统计和运行环境
- `GITHUB_RELEASE_CHECKLIST.md`：首发前检查清单

## 本地运行入口

```bash
cd /opt/blog_access
./run.sh visit
./run.sh report
./run.sh proxy-check
```

## 配置与密钥

### 主配置：`config.json`
放非敏感配置，例如代理、站点、分页数、选择器等。

### 密钥配置：`secrets.json`
放 Telegram 凭据。

解析优先级：
1. 站点内 `tg_token` / `tg_chat`（兼容旧配置）
2. 环境变量 `BLOG_ACCESS_TG_TOKEN` / `BLOG_ACCESS_TG_CHAT`
3. `secrets.json`

## 安装方式

### 方式 1：本地源码安装

```bash
sudo bash setup_blog_access.sh
```

### 方式 2：仅做环境预检查

```bash
sudo BLOG_ACCESS_CHECK_ONLY=1 bash setup_blog_access.sh
```

### 方式 3：显式指定 GitHub 仓库安装

```bash
sudo BLOG_ACCESS_SOURCE_MODE=github \
  BLOG_ACCESS_REPO=https://github.com/owner/repo.git \
  BLOG_ACCESS_REF=main \
  bash setup_blog_access.sh
```

### 方式 4：发布后 curl 一键安装

发布到 GitHub 后，把 `install.sh` 里的默认仓库地址改成真实仓库，然后支持：

```bash
curl -fsSL https://raw.githubusercontent.com/owner/repo/main/install.sh | sudo bash
```

## 发布到 GitHub 前必做

### 1. 不要提交这些文件
- `secrets.json`
- `.env`
- `visit_stats.json`
- `visit_stats.json.bak.*`
- `cron_visit.log`
- `cron_report.log`
- `run_history.jsonl`
- `proxy_check_history.jsonl`
- `venv/`
- `__pycache__/`

### 2. 运行发布前检查

```bash
bash scripts/github_publish_check.sh
```

### 3. 查看首发清单

```bash
cat GITHUB_RELEASE_CHECKLIST.md
```

### 4. 优先提交模板文件
- `config.example.json`
- `secrets.example.json`

新机器初始化后，再复制为真实配置：

```bash
cp config.example.json config.json
cp secrets.example.json secrets.json
```

## 代理出口检测

```bash
./run.sh proxy-check
./run.sh proxy-check 3
```

当前使用 `https://api.ipify.org/?format=text` 作为稳定的纯文本出口查询接口。

## 调试开关

### Dry Run
```bash
BLOG_ACCESS_DRY_RUN=1 ./run.sh report test
```

### Skip Clear
```bash
BLOG_ACCESS_SKIP_CLEAR=1 ./run.sh report test
```

## 当前生产调度（rn 服务器）

```cron
*/40 * * * * cd /opt/blog_access && ./run.sh visit >> ./cron_visit.log 2>&1
30 9 * * * cd /opt/blog_access && ./run.sh report >> ./cron_report.log 2>&1
```
