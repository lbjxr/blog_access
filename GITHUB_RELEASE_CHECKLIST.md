# GitHub 首发清单

在首次发布 `blog_access` 到 GitHub 前，建议按下面顺序检查。

## 1. 保留要提交的文件

建议提交：
- `install.sh`
- `setup_blog_access.sh`
- `scripts/setup_blog_access.sh`
- `scripts/github_publish_check.sh`
- `blog_visit_per_site_v2.py`
- `proxy_utils.py`
- `ip_proxy_check.py`
- `run.sh`
- `requirements.txt`
- `README.md`
- `config.example.json`
- `secrets.example.json`
- `.gitignore`

## 2. 不要提交的文件

确认这些文件没有被 git 跟踪：
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

## 3. 发布前操作建议

### 初始化仓库
```bash
git init
git branch -M main
```

### 先跑检查
```bash
bash scripts/github_publish_check.sh
```

### 查看将提交的内容
```bash
git status --short
```

### 添加文件时优先显式选择
```bash
git add install.sh setup_blog_access.sh scripts/ \
  blog_visit_per_site_v2.py proxy_utils.py ip_proxy_check.py \
  run.sh requirements.txt README.md \
  config.example.json secrets.example.json .gitignore \
  GITHUB_RELEASE_CHECKLIST.md
```

避免一上来直接：
```bash
git add .
```

## 4. 发布前必须替换的占位内容

### `install.sh`
把：
- `https://github.com/OWNER/REPO.git`

替换成你的真实仓库地址。

### `README.md`
如果你要在文档里给出一条 curl 安装命令，记得把：
- `https://raw.githubusercontent.com/owner/repo/main/install.sh`

替换成你的真实 raw 地址。

## 5. 首发后推荐验证

在一台新机器上执行：

```bash
sudo BLOG_ACCESS_CHECK_ONLY=1 bash setup_blog_access.sh
```

如果你已经把 `install.sh` 改成真实仓库，再验证：

```bash
curl -fsSL https://raw.githubusercontent.com/owner/repo/main/install.sh | sudo bash
```

## 6. secrets 使用建议

发布仓库时：
- 提交 `secrets.example.json`
- 不提交 `secrets.json`

新机器部署后：
```bash
cp secrets.example.json secrets.json
vim secrets.json
```

## 7. config 使用建议

发布仓库时：
- 优先提交 `config.example.json`
- `config.json` 若包含真实代理地址、真实站点，也建议不要直接公开提交

新机器部署后：
```bash
cp config.example.json config.json
vim config.json
```
