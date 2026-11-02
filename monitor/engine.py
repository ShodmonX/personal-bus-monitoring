"""Headed Playwright reader; Xvfb DISPLAY is supplied by the container entrypoint."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import Error as PlaywrightError

from monitor.parser import classify_page

LOG = logging.getLogger(__name__)
DEBUG_DIR = Path(os.getenv("DEBUG_DIR", "/app/debug"))
TZ = ZoneInfo("Asia/Tashkent")


async def save_debug(page, slug: str, reason: str) -> None:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(TZ).strftime("%Y%m%d_%H%M%S")
    base = DEBUG_DIR / f"{slug}_{reason}_{stamp}"
    try:
        await page.screenshot(path=str(base) + ".png", full_page=False, timeout=8000)
    except (PlaywrightError, OSError) as exc:
        LOG.warning("Screenshot failed: %s", type(exc).__name__)
    try:
        body = await page.locator("body").inner_text(timeout=8000)
        (Path(str(base) + ".txt")).write_text(body[:12000], encoding="utf-8")
    except (PlaywrightError, OSError) as exc:
        LOG.warning("Page text diagnostic failed: %s", type(exc).__name__)
    LOG.warning("Stop %s: saved diagnostic %s", slug, base.name)


async def read_stop(page, stop: dict) -> tuple[str, list[dict] | None]:
    response = await page.goto(stop["url"], wait_until="domcontentloaded", timeout=60000)
    if response and response.status in {403, 429}:
        await save_debug(page, stop["id"], f"http{response.status}")
        return "limited", None
    if response and response.status >= 500:
        raise RuntimeError(f"Yandex HTTP {response.status}")
    try:
        await page.get_by_text("Прогноз прибытия", exact=False).first.wait_for(
            state="visible", timeout=12000
        )
    except PlaywrightTimeoutError:
        pass
    await page.wait_for_timeout(2500)
    body = await page.locator("body").inner_text(timeout=15000)
    status, arrivals = classify_page(body, page.url, stop)
    if status in {"captcha", "limited", "wrong_page"}:
        await save_debug(page, stop["id"], status)
    return status, arrivals
