from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlparse

import requests


@dataclass(frozen=True)
class ProxySettings:
    server: str
    username: Optional[str] = None
    password: Optional[str] = None
    bypass: Optional[str] = None

    def to_playwright_proxy(self) -> Dict[str, str]:
        proxy: Dict[str, str] = {"server": self.server}
        if self.username:
            proxy["username"] = self.username
        if self.password:
            proxy["password"] = self.password
        if self.bypass:
            proxy["bypass"] = self.bypass
        return proxy

    def redacted(self) -> str:
        auth = ""
        if self.username:
            auth = f"{self.username}:***@"
        return f"{self.server.replace('://', f'://{auth}', 1)}"


def parse_proxy_url(proxy_url: str, bypass: Optional[str] = None) -> ProxySettings:
    raw = (proxy_url or "").strip()
    if not raw:
        raise ValueError("代理 URL 为空")

    parsed = urlparse(raw)
    if parsed.scheme.lower() not in {"http", "https", "socks5"}:
        raise ValueError(f"不支持的代理协议: {parsed.scheme}")
    if not parsed.hostname or not parsed.port:
        raise ValueError("代理 URL 必须包含主机和端口")

    server = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
    username = unquote(parsed.username) if parsed.username else None
    password = unquote(parsed.password) if parsed.password else None

    return ProxySettings(
        server=server,
        username=username,
        password=password,
        bypass=(bypass or None),
    )


def _normalize_proxy_entry(proxy_entry: Any) -> Optional[ProxySettings]:
    if not proxy_entry:
        return None

    if isinstance(proxy_entry, str):
        return parse_proxy_url(proxy_entry)

    if isinstance(proxy_entry, dict):
        if proxy_entry.get("enabled") is False:
            return None

        bypass = proxy_entry.get("bypass")

        if proxy_entry.get("url"):
            return parse_proxy_url(proxy_entry["url"], bypass=bypass)

        server = (proxy_entry.get("server") or "").strip()
        if not server:
            return None

        return ProxySettings(
            server=server,
            username=proxy_entry.get("username") or None,
            password=proxy_entry.get("password") or None,
            bypass=bypass or None,
        )

    raise ValueError(f"不支持的代理配置类型: {type(proxy_entry).__name__}")


def resolve_proxy_config(config: Dict[str, Any], site_config: Dict[str, Any]) -> Optional[ProxySettings]:
    candidates = [
        site_config.get("proxy"),
        config.get("proxy"),
    ]

    for candidate in candidates:
        proxy = _normalize_proxy_entry(candidate)
        if proxy:
            return proxy

    return None


def get_proxy_runtime_options(config: Dict[str, Any]) -> Dict[str, Any]:
    proxy_cfg = config.get("proxy") or {}
    healthcheck_cfg = proxy_cfg.get("healthcheck") or {}
    return {
        "fallback_direct": proxy_cfg.get("fallback_direct", True),
        "healthcheck_enabled": healthcheck_cfg.get("enabled", True),
        "healthcheck_url": healthcheck_cfg.get("url", "https://www.gstatic.com/generate_204"),
        "healthcheck_timeout": healthcheck_cfg.get("timeout", 10),
        "healthcheck_expected_statuses": tuple(healthcheck_cfg.get("expected_statuses", [200, 204, 301, 302])),
    }


def check_proxy_health(
    proxy_settings: ProxySettings,
    test_url: str,
    timeout: int = 10,
    expected_statuses: tuple[int, ...] = (200, 204, 301, 302),
) -> tuple[bool, str]:
    proxies = {
        "http": proxy_settings.server,
        "https": proxy_settings.server,
    }

    auth = None
    if proxy_settings.username and proxy_settings.password:
        auth = f"{proxy_settings.username}:{proxy_settings.password}@"
        proxies = {
            "http": proxy_settings.server.replace("://", f"://{auth}", 1),
            "https": proxy_settings.server.replace("://", f"://{auth}", 1),
        }

    try:
        response = requests.get(test_url, proxies=proxies, timeout=timeout, allow_redirects=True)
        if response.status_code in expected_statuses:
            return True, f"HTTP {response.status_code}"
        return False, f"HTTP {response.status_code}"
    except Exception as exc:
        return False, str(exc)
