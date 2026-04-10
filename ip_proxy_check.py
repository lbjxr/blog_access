import asyncio
import datetime
import json
from pathlib import Path

from playwright.async_api import async_playwright

from proxy_utils import resolve_proxy_config

CONFIG_FILE = Path("/opt/blog_access/config.json")
PROXY_CHECK_HISTORY_FILE = Path("/opt/blog_access/proxy_check_history.jsonl")
TARGET_URL = "https://api.ipify.org/?format=text"


def load_config():
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


async def fetch_ip_once(index: int, proxy: dict | None):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy=proxy,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
            timeout=60000,
        )
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(TARGET_URL, wait_until="load", timeout=60000)
            await page.wait_for_timeout(1500)
            text = (await page.text_content("body") or "").strip()
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            ip = lines[0] if lines else ""
            print(json.dumps({"attempt": index, "url": TARGET_URL, "ip": ip, "raw": text[:200]}, ensure_ascii=False))
            await context.close()
        finally:
            await browser.close()


async def run_proxy_check(count: int = 3):
    config = load_config()
    proxy_settings = resolve_proxy_config(config, {})
    proxy = proxy_settings.to_playwright_proxy() if proxy_settings else None
    results = []
    for i in range(1, count + 1):
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                proxy=proxy,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
                timeout=60000,
            )
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(TARGET_URL, wait_until="load", timeout=60000)
                await page.wait_for_timeout(1500)
                text = (await page.text_content("body") or "").strip()
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                ip = lines[0] if lines else ""
                record = {"attempt": i, "url": TARGET_URL, "ip": ip, "raw": text[:200]}
                results.append(record)
                print(json.dumps(record, ensure_ascii=False))
                await context.close()
            finally:
                await browser.close()
        if i < count:
            await asyncio.sleep(2)

    summary = {
        "ts": datetime.datetime.now().isoformat(),
        "count": count,
        "ips": [item["ip"] for item in results],
        "unique_ips": sorted(set(item["ip"] for item in results if item["ip"])),
        "rotating": len(set(item["ip"] for item in results if item["ip"])) > 1,
    }
    with open(PROXY_CHECK_HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")


async def main():
    await run_proxy_check(count=3)


if __name__ == "__main__":
    asyncio.run(main())
