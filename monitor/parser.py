"""Adapted from the user's working bus_monitor_diagnostic.py parser."""
from __future__ import annotations

import re

CAPTCHA_MARKERS = (
    "я не робот", "подтвердите, что вы не робот", "smartcaptcha",
    "проверка, что вы не робот", "введите символы с картинки",
)


def extract_eta(page_text: str, route: str, destination: str) -> str | None:
    text = page_text.replace("\u00a0", " ").replace("\u202f", " ")
    forecast = re.search(
        r"Прогноз прибытия\s*(.*?)(?:Полное расписание|Смотрите на остановке|Адрес|$)",
        text, re.I | re.S,
    )
    if not forecast:
        return None
    section = forecast.group(1)
    blocks = re.finditer(
        rf"(?m)^\s*{re.escape(route)}\s*$\s*(.*?)(?=^\s*\d{{1,3}}\s*$|\Z)",
        section, re.I | re.M | re.S,
    )
    for match in blocks:
        block = match.group(1)
        if destination.casefold() not in block.casefold():
            continue
        # A service frequency ("Каждые 18 мин") is not an arrival estimate.
        block = re.sub(
            r"\bКажд(?:ые|ую|ый)\s+\d{1,3}\s*мин(?:ут[аы]?)?\b",
            "", block, flags=re.I,
        )
        eta = re.search(r"\b(\d{1,3})\s*(?:мин(?:ут[аы]?)?|min)\b", block, re.I)
        if eta:
            return f"{int(eta.group(1))} daqiqa"
        if re.search(r"\b(?:прибывает|подъезжает|сейчас)\b", block, re.I):
            return "yetib kelmoqda"
    return None


def classify_page(text: str, url: str, stop: dict) -> tuple[str, list[dict] | None]:
    normalized = text.strip().casefold()
    if "captcha" in url.casefold() or any(marker in normalized for marker in CAPTCHA_MARKERS):
        return "captcha", None
    if normalized == "limited" or (len(normalized) < 100 and "limited" in normalized):
        return "limited", None
    if stop["page_stop_name"].casefold() not in normalized:
        return "wrong_page", None
    arrivals = [
        {
            "route": bus["route"],
            "destination": bus["destination"],
            "eta": extract_eta(text, bus["route"], bus["destination"]),
        }
        for bus in stop["buses"]
    ]
    return ("ok" if any(bus["eta"] for bus in arrivals) else "no_eta", arrivals)
