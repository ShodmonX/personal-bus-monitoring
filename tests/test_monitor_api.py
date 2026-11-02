"""API tests without launching a browser or making outside HTTP requests."""
import asyncio
import importlib
import os
from pathlib import Path

import httpx
import pytest

os.environ["MONITOR_API_KEY"] = "test-very-long-private-monitor-key-for-unit-tests"
os.environ["STOPS_FILE"] = str(Path(__file__).resolve().parents[1] / "stops.json")
monitor = importlib.import_module("monitor.app")


def test_session_payload_keeps_each_bus_result():
    arrivals = [
        {"route": "29", "destination": "Пахтакор", "eta": "5 daqiqa"},
        {"route": "72", "destination": "Чорсу", "eta": None},
    ]
    session = monitor.Session(stop_id="eshon-29", status="ok", arrivals=arrivals)
    assert session.payload()["arrivals"] == arrivals


@pytest.mark.asyncio
async def test_monitor_auth_start_status_and_stop(monkeypatch):
    async def fake_worker(_session):
        await asyncio.Event().wait()

    monkeypatch.setattr(monitor, "worker", fake_worker)
    await monitor.stop_all_sessions()
    transport = httpx.ASGITransport(app=monitor.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/watch/eshon-29")).status_code == 403
        headers = {"X-Monitor-Key": os.environ["MONITOR_API_KEY"]}
        assert (await client.get("/watch/missing", headers=headers)).status_code == 404
        started = await client.post("/watch/eshon-29", headers=headers)
        assert started.status_code == 200
        assert started.json()["status"] == "starting"
        assert started.json()["arrivals"] is None
        assert (await client.post("/watch/eshon-29", headers=headers)).status_code == 200
        status = await client.get("/watch/eshon-29", headers=headers)
        assert status.json()["status"] == "starting"
        assert (await client.delete("/watch/eshon-29", headers=headers)).json()["stopped"] is True
        assert (await client.get("/watch/eshon-29", headers=headers)).json()["status"] == "idle"
    await monitor.stop_all_sessions()
