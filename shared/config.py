"""Public stop settings shared by bot and monitor containers."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def load_stops(path: str | None = None) -> dict[str, dict[str, Any]]:
    source = Path(path or os.getenv("STOPS_FILE", "/app/stops.json"))
    entries = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(entries, list) or not entries:
        raise ValueError("stops.json must contain a nonempty list")
    stops: dict[str, dict[str, Any]] = {}
    fields = {"id", "stop_id", "label", "page_stop_name", "url"}
    bus_fields = {"route", "destination", "direction_label"}
    for item in entries:
        if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item[k].strip() for k in fields):
            raise ValueError(f"Invalid stop config; required string fields: {sorted(fields)}")
        slug = item["id"]
        if not slug.isascii() or not all(c.isalnum() or c in "-_" for c in slug) or len(slug) > 35:
            raise ValueError(f"Invalid stop slug: {slug!r}")
        if slug in stops:
            raise ValueError(f"Duplicate stop ID: {slug}")
        parsed = urlparse(item["url"])
        if parsed.scheme != "https" or parsed.hostname not in {"yandex.uz", "yandex.ru", "yandex.com", "yandex.kz"}:
            raise ValueError("Stop URL must be a Yandex Maps HTTPS URL")
        buses = item.get("buses")
        if buses is None and "buses" not in item:
            buses = [{field: item.get(field) for field in bus_fields}]
        if not isinstance(buses, list) or not buses:
            raise ValueError(f"Stop {slug}: buses must be a nonempty list")
        seen: set[tuple[str, str]] = set()
        for bus in buses:
            if not isinstance(bus, dict) or any(
                not isinstance(bus.get(k), str) or not bus[k].strip() for k in bus_fields
            ):
                raise ValueError(f"Stop {slug}: each bus requires {sorted(bus_fields)}")
            key = (bus["route"].casefold(), bus["destination"].casefold())
            if key in seen:
                raise ValueError(f"Duplicate bus direction at stop {slug}: {key}")
            seen.add(key)
        stops[slug] = {**item, "buses": buses}
        for field in bus_fields:
            stops[slug].pop(field, None)
    return stops
