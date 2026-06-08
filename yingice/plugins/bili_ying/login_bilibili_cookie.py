from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

CONFIG_FILE = Path(__file__).with_name("bili_ying_config.json")
LOGIN_URL = "https://passport.bilibili.com/login"
COOKIE_URLS = [
    "https://www.bilibili.com/",
    "https://live.bilibili.com/",
    "https://api.bilibili.com/",
]
DEFAULT_TIMEOUT_SECONDS = 180


def _read_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}

    return data if isinstance(data, dict) else {}


def _write_config(data: dict[str, Any]) -> None:
    with CONFIG_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _format_cookie_header(cookies: list[dict[str, Any]]) -> str:
    cookie_map: dict[str, str] = {}
    for cookie in cookies:
        domain = str(cookie.get("domain") or "")
        name = str(cookie.get("name") or "")
        value = str(cookie.get("value") or "")
        if not name or "bilibili.com" not in domain:
            continue
        cookie_map[name] = value

    return "; ".join(f"{name}={value}" for name, value in sorted(cookie_map.items()))


def _collect_cookie(timeout_seconds: int) -> str:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(  # noqa: TRY003
            "当前环境未安装 playwright，请先执行：pip install playwright"
        ) from exc

    deadline = time.time() + timeout_seconds
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="msedge", headless=False)
        except PlaywrightError:
            browser = playwright.chromium.launch(headless=False)

        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(LOGIN_URL, wait_until="domcontentloaded")
            while time.time() < deadline:
                cookie_header = _format_cookie_header(context.cookies(COOKIE_URLS))
                if "SESSDATA=" in cookie_header:
                    return cookie_header
                page.wait_for_timeout(1000)
        finally:
            browser.close()

    raise TimeoutError("登录超时，未检测到 SESSDATA。")  # noqa: TRY003


def main() -> None:
    parser = argparse.ArgumentParser(
        description="登录 Bilibili 并写入 bili-ying Cookie"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="等待登录的秒数，默认 180 秒",
    )
    args = parser.parse_args()

    print("正在启动浏览器，请登录 Bilibili。")  # noqa: T201
    cookie = _collect_cookie(max(args.timeout, 30))
    config = _read_config()
    config["cookie"] = cookie
    _write_config(config)
    print(f"Cookie 已写入：{CONFIG_FILE}")  # noqa: T201


if __name__ == "__main__":
    main()
