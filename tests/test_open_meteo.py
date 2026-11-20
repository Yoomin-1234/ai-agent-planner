"""Open-Meteo Tool 테스트."""

import pytest
import requests

from app.tools import open_meteo


class FakeResponse:
    def __init__(self, status_code=200, payload=None, json_error=False):
        self.status_code = status_code
        self.payload = payload
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise ValueError("Invalid JSON")
        return self.payload


def sample_payload():
    return {
        "latitude": 37.5,
        "longitude": 127.0,
        "timezone": "Asia/Seoul",
        "current": {
            "time": "2026-11-20T10:00",
            "temperature_2m": 12.5,
            "relative_humidity_2m": 45,
            "apparent_temperature": 11.2,
            "is_day": 1,
            "precipitation": 0.0,
            "rain": 0.0,
            "snowfall": 0.0,
            "weather_code": 0,
            "cloud_cover": 10,
            "wind_speed_10m": 5.4,
            "wind_direction_10m": 180,
        },
        "daily": {
            "time": ["2026-11-20", "2026-11-21"],
            "weather_code": [0, 61],
            "temperature_2m_max": [15.0, 12.0],
            "temperature_2m_min": [7.0, 5.0],
            "precipitation_probability_max": [0, 60],
            "precipitation_sum": [0.0, 3.5],
            "sunrise": [
                "2026-11-20T07:10",
                "2026-11-21T07:11",
            ],
            "sunset": [
                "2026-11-20T17:18",
                "2026-11-21T17:17",
            ],
        },
    }


def test_get_weather_success(monkeypatch):
    captured = {}

    def fake_get(url, params, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return FakeResponse(payload=sample_payload())

    monkeypatch.setattr(open_meteo.requests, "get", fake_get)

    result = open_meteo.get_weather(37.5, 127.0)

    assert result["ok"] is True
    assert result["data"]["timezone"] == "Asia/Seoul"

    current = result["data"]["current"]
    assert current["temperature_c"] == 12.5
    assert current["weather_description"] == "맑음"
    assert current["is_day"] is True

    daily = result["data"]["daily"]
    assert len(daily) == 2
    assert daily[0]["temperature_max_c"] == 15.0
    assert daily[1]["weather_description"] == "약한 비"
    assert daily[1]["precipitation_probability_max_percent"] == 60.0

    assert captured["url"] == open_meteo.FORECAST_URL
    assert captured["params"]["latitude"] == 37.5
    assert captured["params"]["longitude"] == 127.0
    assert captured["params"]["forecast_days"] == 3
    assert captured["params"]["timezone"] == "auto"
    assert captured["timeout"] == open_meteo.REQUEST_TIMEOUT


@pytest.mark.parametrize("latitude", [-91, 91, "37.5", True])
def test_get_weather_invalid_latitude(latitude):
    result = open_meteo.get_weather(latitude, 127.0)

    assert result["ok"] is False
    assert result["error"]["code"] == "BAD_ARGUMENT"


@pytest.mark.parametrize("longitude", [-181, 181, "127.0", False])
def test_get_weather_invalid_longitude(longitude):
    result = open_meteo.get_weather(37.5, longitude)

    assert result["ok"] is False
    assert result["error"]["code"] == "BAD_ARGUMENT"


@pytest.mark.parametrize("forecast_days", [0, 17, -1, 1.5, True, "3"])
def test_get_weather_invalid_forecast_days(forecast_days):
    result = open_meteo.get_weather(
        37.5,
        127.0,
        forecast_days=forecast_days,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "BAD_ARGUMENT"


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (400, "BAD_ARGUMENT"),
        (403, "UPSTREAM_ERROR"),
        (429, "API_LIMIT"),
        (500, "UPSTREAM_ERROR"),
    ],
)
def test_get_weather_http_error(monkeypatch, status_code, expected_code):
    def fake_get(*args, **kwargs):
        return FakeResponse(status_code=status_code)

    monkeypatch.setattr(open_meteo.requests, "get", fake_get)

    result = open_meteo.get_weather(37.5, 127.0)

    assert result["ok"] is False
    assert result["error"]["code"] == expected_code


@pytest.mark.parametrize(
    "exception",
    [
        requests.Timeout(),
        requests.ConnectionError(),
    ],
)
def test_get_weather_request_exception(monkeypatch, exception):
    def fake_get(*args, **kwargs):
        raise exception

    monkeypatch.setattr(open_meteo.requests, "get", fake_get)

    result = open_meteo.get_weather(37.5, 127.0)

    assert result["ok"] is False
    assert result["error"]["code"] == "UPSTREAM_ERROR"


def test_get_weather_invalid_json(monkeypatch):
    def fake_get(*args, **kwargs):
        return FakeResponse(json_error=True)

    monkeypatch.setattr(open_meteo.requests, "get", fake_get)

    result = open_meteo.get_weather(37.5, 127.0)

    assert result["ok"] is False
    assert result["error"]["code"] == "UPSTREAM_ERROR"


def test_get_weather_invalid_response_structure(monkeypatch):
    def fake_get(*args, **kwargs):
        return FakeResponse(payload={
            "current": {},
            "daily": {"time": "not-a-list"},
        })

    monkeypatch.setattr(open_meteo.requests, "get", fake_get)

    result = open_meteo.get_weather(37.5, 127.0)

    assert result["ok"] is False
    assert result["error"]["code"] == "UPSTREAM_ERROR"


def test_get_weather_tool_is_registered():
    from app.tools.registry import catalog

    names = [item["name"] for item in catalog()]

    assert "get_weather" in names
