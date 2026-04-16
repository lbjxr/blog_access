import asyncio
import random
import datetime
import json
import os
import requests
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright
import sys
import time
import socket
from pathlib import Path

from proxy_utils import check_proxy_health, get_proxy_runtime_options, resolve_proxy_config
from ip_proxy_check import run_proxy_check

CONFIG_FILE = "config.json"
SECRETS_FILE = "secrets.json"
STATS_FILE = "visit_stats.json"
RUN_HISTORY_FILE = "run_history.jsonl"
DEFAULT_SELECTORS = {
    "cards": ["div.recent-post-item", "div.post-block"],
    "title_links": ["a.article-title"],
    "fallback_links": ["div.post-button a.btn", "h2.post-title a"],
}

DEVICE_PROFILES = [
    {
        "name": "Desktop_US",
        "viewport": {"width": 1920, "height": 1080},
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "is_mobile": False,
        "has_touch": False,
        "device_scale_factor": 1.0,
        "locales": ["en-US", "es-US"],
        "timezones": [
            "America/New_York",
            "America/Chicago",
            "America/Denver",
            "America/Los_Angeles"
        ]
    },
    {
        "name": "Desktop_EU",
        "viewport": {"width": 1600, "height": 900},
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/118.0",
        "is_mobile": False,
        "has_touch": False,
        "device_scale_factor": 1.0,
        "locales": ["en-GB", "fr-FR", "de-DE"],
        "timezones": [
            "Europe/London",
            "Europe/Paris",
            "Europe/Berlin"
        ]
    },
    {
        "name": "Mobile_Asia",
        "viewport": {"width": 360, "height": 800},
        "user_agent": "Mozilla/5.0 (Linux; Android 13; SM-S901U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36",
        "is_mobile": True,
        "has_touch": True,
        "device_scale_factor": 2.5,
        "locales": ["zh-CN", "ja-JP", "ko-KR"],
        "timezones": [
            "Asia/Shanghai",
            "Asia/Tokyo",
            "Asia/Seoul"
        ]
    }
]


def log(msg):
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def generate_tracking_cookies(url):
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.split(':')[0]
    ts = int(time.time())
    cookies = [
        {
            "name": "_ga",
            "value": f"GA1.2.{random.randint(100000000, 999999999)}.{ts}",
            "domain": domain,
            "path": "/",
            "expires": ts + 3600 * 24 * 7
        },
        {
            "name": "_gid",
            "value": f"GA1.2.{random.randint(100000000, 999999999)}.{ts}",
            "domain": domain,
            "path": "/",
            "expires": ts + 3600 * 24
        },
        {
            "name": "_gat",
            "value": "1",
            "domain": domain,
            "path": "/",
            "expires": ts + 3600
        }
    ]
    return cookies


def load_json_if_exists(path):
    p = Path(path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_config():
    config = load_json_if_exists(CONFIG_FILE)
    secrets = load_json_if_exists(SECRETS_FILE)
    config["_secrets"] = secrets
    return config


def resolve_telegram_target(site, config):
    secrets = config.get("_secrets", {})
    tg = secrets.get("telegram", {}) if isinstance(secrets, dict) else {}
    token = (
        site.get("tg_token")
        or os.environ.get("BLOG_ACCESS_TG_TOKEN")
        or tg.get("default_token")
    )
    chat_id = (
        site.get("tg_chat")
        or os.environ.get("BLOG_ACCESS_TG_CHAT")
        or tg.get("default_chat")
    )
    return token, chat_id


def normalize_site_stats(site_stats):
    site_stats.setdefault("total_visits", 0)
    site_stats.setdefault("successful_visits", 0)
    site_stats.setdefault("failed_visits", 0)
    site_stats.setdefault("proxy_visits", 0)
    site_stats.setdefault("direct_visits", 0)
    site_stats.setdefault("proxy_healthcheck_failures", 0)
    site_stats.setdefault("proxy_launch_failovers", 0)
    site_stats.setdefault("run_count", 0)
    site_stats.setdefault("last_run_articles", 0)
    site_stats.setdefault("last_run_proxy_articles", 0)
    site_stats.setdefault("last_run_direct_articles", 0)
    return site_stats


def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            stats = json.load(f)
        for site_key, site_stats in stats.items():
            if isinstance(site_stats, dict):
                normalize_site_stats(site_stats)
        return stats
    return {}


def save_stats(stats):
    for _, site_stats in stats.items():
        if isinstance(site_stats, dict):
            normalize_site_stats(site_stats)
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=4, ensure_ascii=False)


def append_run_history(entry):
    with open(RUN_HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get_site_selectors(site_config):
    selectors = dict(DEFAULT_SELECTORS)
    custom = site_config.get("selectors", {}) or {}
    for key, value in custom.items():
        if isinstance(value, list) and value:
            selectors[key] = value
    return selectors


def send_telegram_message(token, chat_id, message):
    if not token or not chat_id:
        log("⚠️ Telegram 目标未配置，跳过发送")
        return False

    if os.environ.get("BLOG_ACCESS_DRY_RUN") == "1":
        log("🧪 DRY RUN：跳过 Telegram 实际发送")
        log(f"📝 DRY RUN 报告内容预览:\n{message}")
        return True

    def post_telegram(data):
        return requests.post(url, data=data, timeout=20)

    def parse_payload(resp):
        try:
            return resp.json()
        except Exception:
            return {"ok": False, "description": resp.text[:300]}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    chat_id_str = str(chat_id).strip()
    markdown_data = {
        "chat_id": chat_id_str,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:
        response = post_telegram(markdown_data)
        payload = parse_payload(response)
        if response.ok and payload.get("ok"):
            return True

        description = str(payload.get("description", ""))
        log(
            f"⚠️ Telegram 发送失败(status={response.status_code}) chat_id={chat_id_str}: {description or payload}"
        )

        # 常见故障：Markdown 解析失败，降级为纯文本重试一次
        if response.status_code == 400 and "can't parse entities" in description.lower():
            log("ℹ️ 检测到 Markdown 解析失败，降级为纯文本重试")
            plain_data = {
                "chat_id": chat_id_str,
                "text": message,
                "disable_web_page_preview": True,
            }
            response2 = post_telegram(plain_data)
            payload2 = parse_payload(response2)
            if response2.ok and payload2.get("ok"):
                log("✅ 纯文本降级发送成功")
                return True
            log(
                f"⚠️ 纯文本重试仍失败(status={response2.status_code}) chat_id={chat_id_str}: {payload2.get('description', payload2)}"
            )
        return False
    except requests.RequestException as e:
        log(f"⚠️ 发送 Telegram 消息失败(chat_id={chat_id_str}): {e}")
        return False


async def find_article_from_card(card, selectors):
    for selector in selectors["title_links"]:
        title_a = await card.query_selector(selector)
        if title_a:
            href = await title_a.get_attribute("href")
            title = await title_a.get_attribute("title") or await title_a.inner_text() or "无标题"
            if href:
                return href, title.strip()

    fallback_href = None
    fallback_title = "无标题"
    for selector in selectors["fallback_links"]:
        elem = await card.query_selector(selector)
        if not elem:
            continue
        href = await elem.get_attribute("href")
        title = await elem.get_attribute("title") or await elem.inner_text() or "无标题"
        if href:
            fallback_href = href
            fallback_title = title.strip()
            break

    return fallback_href, fallback_title


async def visit_site(site_config, pages, headless, stats, server_identifier, global_config):
    site_url = site_config["url"].rstrip("/")
    site_key = site_url.replace("https://", "").replace("http://", "")
    if site_key not in stats:
        stats[site_key] = {}
    normalize_site_stats(stats[site_key])

    selectors = get_site_selectors(site_config)
    run_total = 0
    run_success = 0
    run_fail = 0
    run_proxy_articles = 0
    run_direct_articles = 0
    run_started_at = datetime.datetime.now().isoformat()

    log(f"🚀 {server_identifier}开始访问站点: {site_url}")

    proxy_settings = resolve_proxy_config(global_config, site_config)
    proxy_options = get_proxy_runtime_options(global_config)
    use_proxy = False
    proxy_check_detail = "not-configured"

    if proxy_settings:
        log(f"🌐 已配置站点代理: {proxy_settings.redacted()}")
        if proxy_options["healthcheck_enabled"]:
            healthy, detail = check_proxy_health(
                proxy_settings,
                proxy_options["healthcheck_url"],
                timeout=proxy_options["healthcheck_timeout"],
                expected_statuses=proxy_options["healthcheck_expected_statuses"],
            )
            proxy_check_detail = detail
            if healthy:
                use_proxy = True
                log(f"✅ 代理健康检查通过: {detail}")
            else:
                stats[site_key]["proxy_healthcheck_failures"] += 1
                if proxy_options["fallback_direct"]:
                    log(f"⚠️ 代理健康检查失败，回退直连: {detail}")
                else:
                    raise RuntimeError(f"代理健康检查失败且禁止回退直连: {detail}")
        else:
            use_proxy = True
            proxy_check_detail = "healthcheck-skipped"
            log("ℹ️ 已跳过代理健康检查，直接使用代理")
    else:
        log("🌐 当前站点未启用代理，使用 VPS 默认网络")

    async with async_playwright() as p:
        browser = None
        context = None
        home_page = None
        try:
            launch_options = {
                "headless": headless,
                "args": [
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-sync",
                    "--metrics-recording-only",
                    "--mute-audio",
                    "--no-first-run",
                    "--disable-default-apps",
                    "--disable-breakpad",
                    "--disable-features=TranslateUI",
                    "--disk-cache-size=1",
                ],
                "timeout": 60000,
            }
            if use_proxy and proxy_settings:
                launch_options["proxy"] = proxy_settings.to_playwright_proxy()

            try:
                browser = await p.chromium.launch(**launch_options)
            except Exception as launch_error:
                if use_proxy and proxy_options["fallback_direct"]:
                    stats[site_key]["proxy_launch_failovers"] += 1
                    log(f"⚠️ 代理启动浏览器失败，回退直连: {launch_error}")
                    launch_options.pop("proxy", None)
                    use_proxy = False
                    browser = await p.chromium.launch(**launch_options)
                else:
                    raise

            selected_device = random.choice(DEVICE_PROFILES)
            random_timezone = random.choice(selected_device["timezones"])
            random_locale = random.choice(selected_device["locales"])

            context = await browser.new_context(
                user_agent=selected_device["user_agent"],
                viewport=selected_device["viewport"],
                device_scale_factor=selected_device["device_scale_factor"],
                locale=random_locale,
                timezone_id=random_timezone,
                is_mobile=selected_device["is_mobile"],
                has_touch=selected_device["has_touch"]
            )

            home_page = await context.new_page()
            await context.add_cookies(generate_tracking_cookies(site_url))
            await home_page.goto(site_url, timeout=60000)
            await home_page.wait_for_load_state('load')

            try:
                for page_num in range(pages):
                    if page_num > 0:
                        target_url = f"{site_url}/page/{page_num+1}/#content-inner"
                        log(f"➡️ 打开第 {page_num+1} 页: {target_url}")
                        await home_page.goto(target_url, timeout=60000)
                        await home_page.wait_for_load_state('load')
                        await asyncio.sleep(random.randint(3, 7))
                    else:
                        target_url = site_url
                        log(f"📄 首页: {target_url}")

                    scroll_y = random.randint(100, 442)
                    await home_page.evaluate(f"window.scrollBy(0, {scroll_y});")
                    log(f"🔽 页面滚动 {scroll_y} 像素")

                    cards_selector = ", ".join(selectors["cards"])
                    cards = await home_page.query_selector_all(cards_selector)
                    if cards:
                        cards = cards[:10]
                        count = random.randint(3, 5)
                        selected_cards = random.sample(cards, min(count, len(cards)))

                        for card in selected_cards:
                            href, title = await find_article_from_card(card, selectors)
                            if not href:
                                log("⚠️ 找不到文章链接，跳过")
                                continue

                            full_url = urljoin(site_url + "/", href)
                            log(f"📰 新标签页打开文章: {title} ({full_url})")

                            run_total += 1
                            stats[site_key]["total_visits"] += 1
                            if use_proxy:
                                stats[site_key]["proxy_visits"] += 1
                                run_proxy_articles += 1
                            else:
                                stats[site_key]["direct_visits"] += 1
                                run_direct_articles += 1

                            article_page = await context.new_page()
                            article_success = False
                            try:
                                await article_page.goto(full_url, timeout=60000)
                                await article_page.wait_for_load_state('load')

                                scroll_y_article = random.randint(100, 442)
                                await article_page.evaluate(f"window.scrollBy(0, {scroll_y_article})")
                                log(f"🔽 文章页滚动 {scroll_y_article} 像素")

                                stay_time = random.randint(15, 43)
                                log(f"⏳ 文章页停留 {stay_time} 秒")
                                await asyncio.sleep(stay_time)

                                article_success = True
                            except Exception as e:
                                log(f"⚠️ 文章页访问异常: {full_url}, 错误: {e}")
                            finally:
                                await article_page.close()
                                log("↩️ 关闭文章页，回到首页")

                            if article_success:
                                run_success += 1
                                stats[site_key]["successful_visits"] += 1
                            else:
                                run_fail += 1
                                stats[site_key]["failed_visits"] += 1

                            save_stats(stats)
                            await asyncio.sleep(random.randint(3, 7))
                    else:
                        log("⚠️ 没有找到文章卡片，跳过点击")

            except Exception as e:
                log(f"❌ 访问 {site_url} 出错: {e}")

        finally:
            if home_page:
                try:
                    await home_page.close()
                except Exception as e:
                    log(f"⚠️ 关闭首页失败: {e}")
            if context:
                try:
                    await context.close()
                except Exception as e:
                    log(f"⚠️ 关闭上下文失败: {e}")
            if browser:
                try:
                    await browser.close()
                except Exception as e:
                    log(f"⚠️ 关闭浏览器失败: {e}")
            log("🔒 浏览器资源已释放")

    stats[site_key]["run_count"] += 1
    stats[site_key]["last_run_articles"] = run_total
    stats[site_key]["last_run_proxy_articles"] = run_proxy_articles
    stats[site_key]["last_run_direct_articles"] = run_direct_articles
    save_stats(stats)

    success_rate = round(run_success / run_total * 100, 2) if run_total > 0 else 0
    log(f"✅ 完成访问站点: {site_url} 本次访问成功率: {success_rate}%")

    append_run_history({
        "ts": datetime.datetime.now().isoformat(),
        "run_type": "visit",
        "server_identifier": server_identifier,
        "site": site_url,
        "started_at": run_started_at,
        "ended_at": datetime.datetime.now().isoformat(),
        "articles": run_total,
        "successful": run_success,
        "failed": run_fail,
        "proxy_used": use_proxy,
        "proxy_check_detail": proxy_check_detail,
        "proxy_articles": run_proxy_articles,
        "direct_articles": run_direct_articles,
    })


def build_site_report_block(site_url, stats):
    site_key = site_url.replace("https://", "").replace("http://", "")
    data = normalize_site_stats(stats.get(site_key, {}))
    total = data.get("total_visits", 0)
    success = data.get("successful_visits", 0)
    fail = data.get("failed_visits", 0)
    proxy_visits = data.get("proxy_visits", 0)
    direct_visits = data.get("direct_visits", 0)
    proxy_healthcheck_failures = data.get("proxy_healthcheck_failures", 0)
    proxy_launch_failovers = data.get("proxy_launch_failovers", 0)

    lines = [
        f"🌐 站点: {site_url}",
        f"📈 总访问: {total}",
        f"✅ 成功: {success} | ❌ 失败: {fail}",
        f"🌍 代理: {proxy_visits} | 直连: {direct_visits}",
    ]

    if proxy_healthcheck_failures or proxy_launch_failovers:
        lines.append(
            f"🛡 健康失败: {proxy_healthcheck_failures} | 回退直连: {proxy_launch_failovers}"
        )

    return "\n".join(lines)


def send_daily_report(config, stats, server_identifier):
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    date_str = yesterday.strftime("%Y-%m-%d")
    dry_run = os.environ.get("BLOG_ACCESS_DRY_RUN") == "1"
    skip_clear = os.environ.get("BLOG_ACCESS_SKIP_CLEAR") == "1"
    all_sent = True

    grouped_targets = {}
    for site in config["sites"]:
        site_url = site["url"].rstrip("/")
        token, chat_id = resolve_telegram_target(site, config)
        target_key = (token, str(chat_id).strip() if chat_id is not None else "")
        grouped_targets.setdefault(target_key, []).append(site_url)

    for (token, chat_id), site_urls in grouped_targets.items():
        header = (
            f"📊 博客访问统计日报\n"
            f"【基础信息】\n"
            f"🖥 主机: {server_identifier}\n"
            f"📅 日期: {date_str}"
        )
        site_blocks = [build_site_report_block(site_url, stats) for site_url in site_urls]
        message = header + "\n\n" + "\n\n".join(site_blocks)

        sent = send_telegram_message(token, chat_id, message)
        if sent:
            log(f"✅ 报告发送完成: {len(site_urls)} 个站点 -> chat_id={chat_id}")
        else:
            all_sent = False
            log(f"⚠️ 报告发送失败: {len(site_urls)} 个站点 -> chat_id={chat_id}")

        for site_url in site_urls:
            append_run_history({
                "ts": datetime.datetime.now().isoformat(),
                "run_type": "report",
                "server_identifier": server_identifier,
                "site": site_url,
                "sent": sent,
                "dry_run": dry_run,
                "skip_clear": skip_clear,
                "delivery_mode": "grouped_message",
                "grouped_site_count": len(site_urls),
            })

    if dry_run:
        log("🧪 DRY RUN：跳过清空统计数据文件。")
    elif skip_clear:
        log("🧪 SKIP CLEAR：已发送报告，但保留统计数据文件。")
    elif not all_sent:
        log("⚠️ 存在发送失败，保留统计数据文件，避免丢失待重发数据。")
    else:
        if os.path.exists(STATS_FILE):
            os.remove(STATS_FILE)
        log("✅ 发送完毕，已清空统计数据文件。")

async def main():
    if len(sys.argv) < 2:
        print("用法: python script.py [visit|report|proxy-check] [server_identifier|count]")
        print("示例: python script.py visit vps1")
        print("示例: python script.py report")
        print("示例: python script.py proxy-check 3")
        return

    command = sys.argv[1].lower()
    if len(sys.argv) >= 3:
        server_identifier = sys.argv[2]
    else:
        server_identifier = socket.gethostname()

    config = load_config()

    if command == "visit":
        stats = load_stats()
        sites = config["sites"]
        for i, site in enumerate(sites):
            log(f"🌐 开始访问站点 {i+1}/{len(sites)}: {site['url']}")
            await visit_site(site, config["pages"], config["headless"], stats, server_identifier, config)
            save_stats(stats)
            if i < len(sites) - 1:
                cooldown = random.randint(30, 60)
                log(f"😴 站点访问完成，休息 {cooldown} 秒...")
                await asyncio.sleep(cooldown)
            log(f"💾 [{server_identifier}] 已保存 {site['url']} 的统计数据")
    elif command == "report":
        stats = load_stats()
        send_daily_report(config, stats, server_identifier)
    elif command == "proxy-check":
        count = 3
        if len(sys.argv) >= 3:
            try:
                count = max(1, int(sys.argv[2]))
            except ValueError:
                print("proxy-check 的次数参数必须是整数，例如: python script.py proxy-check 3")
                return
        await run_proxy_check(count=count)
    else:
        print("无效命令，支持 visit、report 和 proxy-check。")


if __name__ == "__main__":
    asyncio.run(main())
