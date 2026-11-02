"""Telegram monitoring xabarlari."""

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Tashkent")


def format_report(
    stop: dict[str, Any],
    payload: dict,
    now: datetime | None = None,
) -> str:
    now = (now or datetime.now(TZ)).astimezone(TZ)
    status = payload.get("status", "error")

    heading = f"📍 {stop['label']}"

    details = {
        "no_eta": "⏳ Hozircha kelish prognozi mavjud emas",
        "starting": "🔄 Prognoz yuklanmoqda...",
        "captcha": "⚠️ Yandex robot tekshiruvini so‘rayapti.",
        "limited": "⚠️ Yandex sahifani chekladi. 5 daqiqa tanaffus.",
        "wrong_page": "⚠️ Bekat sahifasi yuklanmadi.",
        "error": "⚠️ Monitoring xatosi. Qayta ulanmoqda.",
        "idle": "⛔ Monitoring to‘xtagan. Qayta boshlang.",
    }

    checked = payload.get("checked_at")
    checked_at = now

    if checked:
        try:
            checked_at = datetime.fromisoformat(
                checked
            ).astimezone(TZ)
        except (ValueError, TypeError):
            pass

    # Eski ETA asosida noto‘g‘ri kelish vaqtini chiqarmaymiz.
    if status in {"ok", "no_eta"}:
        age = (now - checked_at).total_seconds()

        if checked and age > 120:
            return (
                f"{heading}\n"
                "⚠️ Oxirgi prognoz eskirgan. "
                "Yangilanish kutilmoqda."
            )

    if status not in {"ok", "no_eta"}:
        return f"{heading}\n{details.get(status, '⚠️ Noma’lum holat')}"

    arrivals = {
        (item["route"], item["destination"]): item.get("eta")
        for item in payload.get("arrivals") or []
    }
    lines = [heading]
    for bus in stop["buses"]:
        eta = arrivals.get((bus["route"], bus["destination"]))
        label = f"🚌 {bus['route']} → {bus['direction_label']}"
        if eta == "yetib kelmoqda":
            detail = "🟢 Avtobus yetib kelmoqda"
        elif eta:
            detail = f"⏱ {eta}"
            try:
                minutes = int(eta.split()[0])
                arrival = (checked_at + timedelta(minutes=minutes) + timedelta(seconds=30)).replace(
                    second=0, microsecond=0
                )
                detail += f" · {arrival:%H:%M}"
            except (ValueError, IndexError):
                pass
        else:
            detail = details["no_eta"]
        lines.append(f"{label}: {detail}")
    return "\n".join(lines)
