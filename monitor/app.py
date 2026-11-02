"""Internal monitor API. No host port is published in docker compose."""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from monitor.engine import read_stop
from shared.config import load_stops

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
LOG = logging.getLogger("monitor")
TZ = ZoneInfo("Asia/Tashkent")
STOPS = load_stops()
API_KEY = os.environ.get("MONITOR_API_KEY", "")
if len(API_KEY) < 24:
    raise RuntimeError("MONITOR_API_KEY must be at least 24 characters")
SCRAPE_INTERVAL = max(20, int(os.getenv("SCRAPE_INTERVAL_SECONDS", "30")))
MAX_ACTIVE = max(1, int(os.getenv("MAX_ACTIVE_STOPS", "1")))


@dataclass
class Session:
    stop_id: str
    status: str = "starting"
    arrivals: list[dict] | None = None
    checked_at: str | None = None
    task: asyncio.Task | None = field(default=None, repr=False)

    def payload(self) -> dict:
        return {
            "stop_id": self.stop_id,
            "status": self.status,
            "arrivals": self.arrivals,
            "checked_at": self.checked_at,
        }


sessions: dict[str, Session] = {}
lock = asyncio.Lock()


def timestamp() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def authenticate(x_monitor_key: str | None = Header(None)) -> None:
    if not x_monitor_key or not hmac.compare_digest(x_monitor_key, API_KEY):
        raise HTTPException(403, detail="Forbidden")


async def worker(session: Session) -> None:
    stop = STOPS[session.stop_id]
    while True:
        browser = None
        context = None
        playwright = None
        try:
            session.status, session.arrivals = "starting", None
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=False)
            context = await browser.new_context(locale="ru-RU", timezone_id="Asia/Tashkent")
            page = await context.new_page()
            LOG.info("Headed Chromium launched for %s", session.stop_id)
            while True:
                tick = asyncio.get_running_loop().time()
                status, arrivals = await read_stop(page, stop)
                session.status, session.arrivals, session.checked_at = status, arrivals, timestamp()
                LOG.info("%s status=%s arrivals=%s", session.stop_id, status, arrivals)
                if status in {"captcha", "limited", "wrong_page"}:
                    # Respect an access restriction: do not hammer/retry rapidly.
                    await asyncio.sleep(300)
                else:
                    elapsed = asyncio.get_running_loop().time() - tick
                    await asyncio.sleep(max(0, SCRAPE_INTERVAL - elapsed))
        except asyncio.CancelledError:
            raise
        except (PlaywrightError, RuntimeError, asyncio.TimeoutError) as exc:
            LOG.warning("%s browser error: %s", session.stop_id, type(exc).__name__)
            session.status, session.arrivals, session.checked_at = "error", None, timestamp()
            await asyncio.sleep(15)
        except Exception as exc:
            LOG.exception("%s unexpected monitor error", session.stop_id)
            session.status, session.arrivals, session.checked_at = "error", None, timestamp()
            await asyncio.sleep(30)
        finally:
            if context:
                with suppress(Exception):
                    await asyncio.wait_for(context.close(), timeout=8)
            if browser:
                with suppress(Exception):
                    if browser.is_connected():
                        await asyncio.wait_for(browser.close(), timeout=10)
            if playwright:
                with suppress(Exception):
                    await asyncio.wait_for(playwright.stop(), timeout=10)


async def stop_all_sessions() -> None:
    async with lock:
        items = list(sessions.values())
        sessions.clear()
    for item in items:
        if item.task:
            item.task.cancel()
    for item in items:
        if item.task:
            with suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(item.task, timeout=20)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await stop_all_sessions()


app = FastAPI(title="Internal bus monitor", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/stops", dependencies=[Depends(authenticate)])
async def list_stops():
    return list(STOPS.values())


@app.post("/watch/{stop_id}", dependencies=[Depends(authenticate)])
async def start_watch(stop_id: str):
    if stop_id not in STOPS:
        raise HTTPException(404, "Unknown stop")
    async with lock:
        if stop_id in sessions:
            return sessions[stop_id].payload()
        if len(sessions) >= MAX_ACTIVE:
            raise HTTPException(409, f"At most {MAX_ACTIVE} active monitoring session(s)")
        session = Session(stop_id=stop_id)
        sessions[stop_id] = session
        session.task = asyncio.create_task(worker(session), name=f"watch-{stop_id}")
        return session.payload()


@app.get("/watch/{stop_id}", dependencies=[Depends(authenticate)])
async def get_watch(stop_id: str):
    if stop_id not in STOPS:
        raise HTTPException(404, "Unknown stop")
    session = sessions.get(stop_id)
    return session.payload() if session else {"stop_id": stop_id, "status": "idle", "arrivals": None, "checked_at": None}


@app.delete("/watch/{stop_id}", dependencies=[Depends(authenticate)])
async def stop_watch(stop_id: str):
    async with lock:
        session = sessions.pop(stop_id, None)
    if session and session.task:
        session.task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await asyncio.wait_for(session.task, timeout=20)
    return {"stopped": bool(session)}


@app.post("/stop-all", dependencies=[Depends(authenticate)])
async def stop_everything():
    await stop_all_sessions()
    return {"stopped": True}
