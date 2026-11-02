"""Docker Xvfb one-shot smoke test; check actual ETA outside API service."""
import asyncio
import logging

from playwright.async_api import async_playwright

from monitor.engine import read_stop
from shared.config import load_stops


async def main():
    stop = next(iter(load_stops().values()))
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        try:
            context = await browser.new_context(locale="ru-RU", timezone_id="Asia/Tashkent")
            page = await context.new_page()
            status, arrivals = await read_stop(page, stop)
            print(f"Stop={stop['label']} | status={status}")
            for arrival in arrivals or []:
                print(f"  {arrival['route']} → {arrival['destination']}: {arrival['eta'] or '-'}")
            if status not in {"ok", "no_eta"}:
                raise SystemExit(2)
        finally:
            await browser.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
