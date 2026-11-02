"""Personal Telegram interface; only one authorized private Telegram user."""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes

from bot.messages import format_report
from shared.config import load_stops

LOG = logging.getLogger("telegram-bus")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
STOPS = load_stops()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
USER_ID = int(os.getenv("TELEGRAM_ALLOWED_USER_ID", "0"))
API_KEY = os.getenv("MONITOR_API_KEY", "")
MONITOR_URL = os.getenv("MONITOR_URL", "http://monitor:8099").rstrip("/")
NOTIFY_INTERVAL = max(60, int(os.getenv("NOTIFY_INTERVAL_SECONDS", "60")))

if not TOKEN or USER_ID <= 0 or len(API_KEY) < 24:
    raise RuntimeError("Set TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_ID, MONITOR_API_KEY")


@dataclass
class Watch:
    stop_id: str
    chat_id: int
    task: asyncio.Task | None = None
    last_message_id: int | None = None
    active: bool = True


def state(app: Application) -> dict[str, Watch]:
    return app.bot_data.setdefault("watches", {})


def api(app: Application) -> httpx.AsyncClient:
    return app.bot_data["api"]


def keyboard(app: Application) -> InlineKeyboardMarkup:
    rows = []
    for slug, stop in STOPS.items():
        running = slug in state(app)
        icon = "⏹" if running else "▶️"
        label = "To‘xtatish" if running else "Kuzatish"
        action = "stop" if running else "start"
        routes = ", ".join(dict.fromkeys(bus["route"] for bus in stop["buses"]))
        rows.append([InlineKeyboardButton(
            f"{icon} {stop['label']} · {routes} — {label}",
            callback_data=f"{action}:{slug}",
        )])
    return InlineKeyboardMarkup(rows)


def notice_stop_button(slug: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(
        "⏹ Kuzatishni to‘xtatish", callback_data=f"stop:{slug}"
    )]])


def authorized(update: Update) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    return bool(user and chat and user.id == USER_ID and chat.type == "private")


async def refresh_menu(app: Application, chat_id: int) -> None:
    menu_id = app.bot_data.get("menu_message_id")
    if not menu_id:
        return
    try:
        await app.bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=menu_id, reply_markup=keyboard(app)
        )
    except TelegramError as exc:
        if "not modified" not in str(exc).casefold():
            LOG.warning("Menu update failed: %s", type(exc).__name__)


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    old_id = context.application.bot_data.get("menu_message_id")
    if old_id:
        with suppress(TelegramError):
            await context.bot.delete_message(update.effective_chat.id, old_id)
    msg = await update.effective_message.reply_text(
        "🚌 Bekatni tanlang. Kuzatuvni istalgan payt to‘xtatishingiz mumkin:",
        reply_markup=keyboard(context.application),
    )
    context.application.bot_data["menu_message_id"] = msg.message_id

async def delete_later(bot, chat_id: int, message_id: int):
    await asyncio.sleep(30)

    with suppress(TelegramError):
        await bot.delete_message(
            chat_id=chat_id,
            message_id=message_id,
        )

async def replace_notification(app: Application, watch: Watch, text: str) -> None:
    # Delete old message FIRST. A message manually deleted by the user is harmless.
    old_id = watch.last_message_id
    watch.last_message_id = None
    if old_id:
        with suppress(TelegramError):
            await app.bot.delete_message(chat_id=watch.chat_id, message_id=old_id)
    msg = await app.bot.send_message(
        chat_id=watch.chat_id,
        text=text,
        reply_markup=notice_stop_button(watch.stop_id) if watch.active else None,
        disable_notification=False,
    )
    watch.last_message_id = msg.message_id


async def notification_loop(app: Application, watch: Watch) -> None:
    slug = watch.stop_id
    stop = STOPS[slug]
    # Wait briefly for first Playwright scrape, without delaying callback handling.
    deadline = asyncio.get_running_loop().time() + 35
    try:
        while watch.active and asyncio.get_running_loop().time() < deadline:
            try:
                resp = await api(app).get(f"/watch/{slug}")
                resp.raise_for_status()
                if resp.json().get("status") not in {"starting", None}:
                    break
            except httpx.HTTPError:
                break
            await asyncio.sleep(3)

        while watch.active:
            tick = asyncio.get_running_loop().time()
            try:
                resp = await api(app).get(f"/watch/{slug}")
                resp.raise_for_status()
                result = resp.json()
                if result.get("status") == "idle":
                    watch.active = False
                    state(app).pop(slug, None)
                    await replace_notification(app, watch, format_report(stop, result))
                    await refresh_menu(app, watch.chat_id)
                    return
            except (httpx.HTTPError, ValueError) as exc:
                LOG.warning("Monitor API unavailable (%s): %s", slug, type(exc).__name__)
                result = {"status": "error", "arrivals": None, "checked_at": None}
            try:
                await replace_notification(app, watch, format_report(stop, result))
            except TelegramError as exc:
                LOG.warning("Notification failed (%s): %s", slug, type(exc).__name__)
            elapsed = asyncio.get_running_loop().time() - tick
            await asyncio.sleep(max(0, NOTIFY_INTERVAL - elapsed))
    except asyncio.CancelledError:
        raise
    except Exception:
        LOG.exception("Notification loop crashed: %s", slug)
        watch.active = False
        if state(app).get(slug) is watch:
            state(app).pop(slug, None)
        with suppress(Exception):
            await api(app).delete(f"/watch/{slug}")
        with suppress(TelegramError):
            await app.bot.send_message(chat_id=watch.chat_id, text="⚠️ Bot monitoringi xatolik tufayli to‘xtadi. /start bosing.")
        await refresh_menu(app, watch.chat_id)


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    if not authorized(update):
        await query.answer("Ruxsat yo‘q", show_alert=True)
        return
    if not query.data or ":" not in query.data:
        await query.answer("Noto‘g‘ri buyruq")
        return
    action, slug = query.data.split(":", 1)
    if slug not in STOPS or action not in {"start", "stop"}:
        await query.answer("Noma’lum bekat")
        return
    await query.answer()
    app = context.application
    watches = state(app)

    if action == "start":
        if slug in watches:
            await refresh_menu(app, update.effective_chat.id)
            return
        try:
            response = await api(app).post(f"/watch/{slug}")
            if response.status_code == 409:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="⚠️ Hozircha faqat bitta bekatni kuzatish mumkin. Avval aktiv kuzatuvni to‘xtating.",
                )
                return
            response.raise_for_status()
        except httpx.HTTPError as exc:
            LOG.warning("Cannot start monitor: %s", type(exc).__name__)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ Monitoring servisiga ulanib bo‘lmadi. Docker loglarini tekshiring.",
            )
            return
        watch = Watch(stop_id=slug, chat_id=update.effective_chat.id)
        watches[slug] = watch
        watch.task = asyncio.create_task(notification_loop(app, watch), name=f"telegram-{slug}")
        await refresh_menu(app, watch.chat_id)
        return

    watch = watches.get(slug)
    if not watch:
        await refresh_menu(app, update.effective_chat.id)
        return
    watch.active = False
    if watch.task:
        watch.task.cancel()
        with suppress(asyncio.CancelledError):
            await watch.task
    try:
        response = await api(app).delete(f"/watch/{slug}")
        response.raise_for_status()
        stopped_text = f"⏹ {STOPS[slug]['label']}: kuzatuv to‘xtatildi."
    except httpx.HTTPError:
        stopped_text = "⚠️ Telegram kuzatuvi to‘xtadi, ammo monitoring servisini to‘xtatib bo‘lmadi. Docker loglarini tekshiring."
    watches.pop(slug, None)
    if watch.last_message_id:
        with suppress(TelegramError):
            await context.bot.delete_message(
                watch.chat_id,
                watch.last_message_id,
            )
    await refresh_menu(app, watch.chat_id)
    msg = await context.bot.send_message(
        chat_id=watch.chat_id,
        text=stopped_text,
    )

    asyncio.create_task(
        delete_later(
            context.bot,
            watch.chat_id,
            msg.message_id,
        )
    )

async def on_start(app: Application) -> None:
    # A bot restart must never leave a ghost Chromium session in the monitor.
    app.bot_data["watches"] = {}
    app.bot_data["api"] = httpx.AsyncClient(
        base_url=MONITOR_URL,
        headers={"X-Monitor-Key": API_KEY},
        timeout=httpx.Timeout(45.0, connect=5.0),
    )
    try:
        response = await api(app).post("/stop-all")
        response.raise_for_status()
        LOG.info("Monitor startup reconciliation OK: stopped old sessions")
    except httpx.HTTPError as exc:
        LOG.warning("Startup reconciliation failed: %s", type(exc).__name__)


async def on_stop(app: Application) -> None:
    for watch in list(state(app).values()):
        watch.active = False
        if watch.task:
            watch.task.cancel()
            with suppress(asyncio.CancelledError):
                await watch.task
    state(app).clear()
    try:
        await api(app).post("/stop-all")
    except httpx.HTTPError:
        LOG.warning("Could not stop monitor on bot shutdown")
    await api(app).aclose()


def main() -> None:
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(on_start)
        .post_stop(on_stop)
        .build()
    )
    app.add_handler(CommandHandler("start", show_menu))
    app.add_handler(CommandHandler("menu", show_menu))
    app.add_handler(CallbackQueryHandler(handle_button, pattern=r"^(start|stop):[A-Za-z0-9_-]+$"))
    LOG.info("Telegram polling started for one authorized user")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
