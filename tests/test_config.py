import json
import pytest
from shared.config import load_stops


def test_current_stops():
    cfg = load_stops("stops.json")
    assert "eshon-29" in cfg
    assert cfg["eshon-29"]["buses"][0]["route"] == "29"


def test_multiple_buses_at_one_stop(tmp_path):
    stop = dict(next(iter(load_stops("stops.json").values())))
    stop["buses"] = [
        {"route": "29", "destination": "Пахтакор", "direction_label": "Metro Paxtakor"},
        {"route": "72", "destination": "Чорсу", "direction_label": "Chorsu"},
    ]
    p = tmp_path / "multiple.json"
    p.write_text(json.dumps([stop], ensure_ascii=False), encoding="utf-8")
    assert [bus["route"] for bus in load_stops(str(p))[stop["id"]]["buses"]] == ["29", "72"]


def test_legacy_single_bus_is_normalized(tmp_path):
    stop = dict(next(iter(load_stops("stops.json").values())))
    bus = stop.pop("buses")[0]
    stop.update(bus)
    p = tmp_path / "legacy.json"
    p.write_text(json.dumps([stop], ensure_ascii=False), encoding="utf-8")
    assert load_stops(str(p))[stop["id"]]["buses"] == [bus]


def test_duplicate_bus_direction_rejected(tmp_path):
    stop = dict(next(iter(load_stops("stops.json").values())))
    stop["buses"] = [stop["buses"][0], stop["buses"][0]]
    p = tmp_path / "duplicate-bus.json"
    p.write_text(json.dumps([stop], ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate bus"):
        load_stops(str(p))


def test_duplicate_rejected(tmp_path):
    stop = next(iter(load_stops("stops.json").values()))
    p = tmp_path / "duplicate.json"
    p.write_text(json.dumps([stop, stop]), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        load_stops(str(p))


def test_invalid_url_rejected(tmp_path):
    stop = dict(next(iter(load_stops("stops.json").values())))
    stop["url"] = "http://other.example/"
    p = tmp_path / "bad.json"
    p.write_text(json.dumps([stop]), encoding="utf-8")
    with pytest.raises(ValueError, match="Yandex"):
        load_stops(str(p))
