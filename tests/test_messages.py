from datetime import datetime, timedelta, timezone
from bot.messages import format_report
from shared.config import load_stops

STOP = next(iter(load_stops("stops.json").values()))
NOW = datetime(2026, 9, 24, 8, 42, tzinfo=timezone(timedelta(hours=5)))


def test_short_eta_message():
    msg = format_report(STOP, {"status": "ok", "arrivals": [{"route": "29", "destination": "Пахтакор", "eta": "5 daqiqa"}], "checked_at": NOW.isoformat()}, NOW)
    assert "5 daqiqa" in msg and "Metro Paxtakor" in msg and "08:47" in msg


def test_missing_eta_and_limited():
    assert "Hozircha kelish prognozi mavjud emas" in format_report(STOP, {"status": "no_eta"}, NOW)
    assert "5 daqiqa tanaffus" in format_report(STOP, {"status": "limited"}, NOW)


def test_each_selected_bus_has_own_result():
    stop = dict(STOP)
    stop["buses"] = [
        STOP["buses"][0],
        {"route": "72", "destination": "Чорсу", "direction_label": "Chorsu"},
    ]
    msg = format_report(stop, {"status": "ok", "arrivals": [
        {"route": "29", "destination": "Пахтакор", "eta": "5 daqiqa"},
        {"route": "72", "destination": "Чорсу", "eta": None},
    ], "checked_at": NOW.isoformat()}, NOW)
    assert "29 → Metro Paxtakor" in msg and "5 daqiqa" in msg
    assert "72 → Chorsu" in msg and "Hozircha kelish prognozi mavjud emas" in msg


def test_stale_eta_is_not_reported():
    old = NOW - timedelta(minutes=3)
    msg = format_report(STOP, {"status": "ok", "arrivals": [{"route": "29", "destination": "Пахтакор", "eta": "5 daqiqa"}], "checked_at": old.isoformat()}, NOW)
    assert "eskirgan" in msg and "5 daqiqa" not in msg
