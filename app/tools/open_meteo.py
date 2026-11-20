"""Open-Meteo 현재 날씨 및 일별 예보 조회 Tool."""

import math

import requests

from .base import Tool, fail, ok


FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT = 10

CURRENT_FIELDS = (
    "temperature_2m,"
    "relative_humidity_2m,"
    "apparent_temperature,"
    "is_day,"
    "precipitation,"
    "rain,"
    "snowfall,"
    "weather_code,"
    "cloud_cover,"
    "wind_speed_10m,"
    "wind_direction_10m"
)

DAILY_FIELDS = (
    "weather_code,"
    "temperature_2m_max,"
    "temperature_2m_min,"
    "precipitation_probability_max,"
    "precipitation_sum,"
    "sunrise,"
    "sunset"
)

# Open-Meteo가 반환하는 WMO 날씨 코드의 한국어 설명
WEATHER_CODES = {
    0: "맑음",
    1: "대체로 맑음",
    2: "부분적으로 흐림",
    3: "흐림",
    45: "안개",
    48: "서리 안개",
    51: "약한 이슬비",
    53: "보통 이슬비",
    55: "강한 이슬비",
    56: "약한 어는 이슬비",
    57: "강한 어는 이슬비",
    61: "약한 비",
    63: "보통 비",
    65: "강한 비",
    66: "약한 어는 비",
    67: "강한 어는 비",
    71: "약한 눈",
    73: "보통 눈",
    75: "강한 눈",
    77: "싸락눈",
    80: "약한 소나기",
    81: "보통 소나기",
    82: "강한 소나기",
    85: "약한 눈소나기",
    86: "강한 눈소나기",
    95: "뇌우",
    96: "약한 우박을 동반한 뇌우",
    99: "강한 우박을 동반한 뇌우",
}


def _is_valid_coordinate(value: object, minimum: float, maximum: float) -> bool:
    """좌표가 유한한 숫자이고 허용 범위 안에 있는지 확인한다."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and minimum <= value <= maximum
    )


def _number_or_none(value: object) -> float | None:
    """외부 응답의 숫자 값을 안전하게 변환한다."""
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    ):
        return float(value)
    return None


def _weather_code_or_none(value: object) -> int | None:
    """날씨 코드를 정수로 변환한다."""
    number = _number_or_none(value)

    if number is None or not number.is_integer():
        return None

    return int(number)


def _weather_description(code: int | None) -> str | None:
    """WMO 날씨 코드를 한국어 설명으로 변환한다."""
    if code is None:
        return None

    return WEATHER_CODES.get(code, "알 수 없는 날씨 코드")


def _daily_value(daily: dict, field: str, index: int):
    """일별 배열에서 인덱스에 해당하는 값을 안전하게 가져온다."""
    values = daily.get(field)

    if not isinstance(values, list) or index >= len(values):
        return None

    return values[index]


def get_weather(
    latitude: float,
    longitude: float,
    forecast_days: int = 3,
) -> dict:
    """위도·경도를 기준으로 현재 날씨와 일별 예보를 조회한다."""

    if not _is_valid_coordinate(latitude, -90, 90):
        return fail(
            "BAD_ARGUMENT",
            "latitude는 -90부터 90 사이의 유효한 숫자여야 합니다.",
        )

    if not _is_valid_coordinate(longitude, -180, 180):
        return fail(
            "BAD_ARGUMENT",
            "longitude는 -180부터 180 사이의 유효한 숫자여야 합니다.",
        )

    if (
        not isinstance(forecast_days, int)
        or isinstance(forecast_days, bool)
        or not 1 <= forecast_days <= 16
    ):
        return fail(
            "BAD_ARGUMENT",
            "forecast_days는 1부터 16 사이의 정수여야 합니다.",
        )

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": CURRENT_FIELDS,
        "daily": DAILY_FIELDS,
        "forecast_days": forecast_days,
        "timezone": "auto",
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }

    try:
        response = requests.get(
            FORECAST_URL,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

    except requests.Timeout:
        return fail(
            "UPSTREAM_ERROR",
            "Open-Meteo 요청 시간이 초과되었습니다.",
        )

    except requests.ConnectionError:
        return fail(
            "UPSTREAM_ERROR",
            "Open-Meteo 서버에 연결할 수 없습니다.",
        )

    except requests.RequestException:
        return fail(
            "UPSTREAM_ERROR",
            "Open-Meteo 요청 중 오류가 발생했습니다.",
        )

    status_code = response.status_code

    if status_code == 400:
        return fail(
            "BAD_ARGUMENT",
            "Open-Meteo 요청 인자가 올바르지 않습니다.",
        )

    if status_code == 429:
        return fail(
            "API_LIMIT",
            "Open-Meteo API 호출 한도에 도달했습니다.",
        )

    if status_code >= 500:
        return fail(
            "UPSTREAM_ERROR",
            "Open-Meteo 서버에서 오류가 발생했습니다.",
        )

    if status_code >= 400:
        return fail(
            "UPSTREAM_ERROR",
            "Open-Meteo 요청을 처리하지 못했습니다.",
        )

    try:
        payload = response.json()
    except (ValueError, TypeError):
        return fail(
            "UPSTREAM_ERROR",
            "Open-Meteo 응답을 JSON으로 읽을 수 없습니다.",
        )

    if not isinstance(payload, dict):
        return fail(
            "UPSTREAM_ERROR",
            "Open-Meteo 응답 형식이 올바르지 않습니다.",
        )

    current = payload.get("current")
    daily = payload.get("daily")

    if not isinstance(current, dict) or not isinstance(daily, dict):
        return fail(
            "UPSTREAM_ERROR",
            "Open-Meteo 날씨 데이터 형식이 올바르지 않습니다.",
        )

    dates = daily.get("time")

    if (
        not isinstance(dates, list)
        or not dates
        or not all(isinstance(date, str) for date in dates)
    ):
        return fail(
            "UPSTREAM_ERROR",
            "Open-Meteo 일별 예보 데이터가 올바르지 않습니다.",
        )

    current_code = _weather_code_or_none(current.get("weather_code"))

    current_is_day = current.get("is_day")
    if current_is_day in (0, 1) and not isinstance(current_is_day, bool):
        current_is_day = bool(current_is_day)
    else:
        current_is_day = None

    current_result = {
        "time": current.get("time"),
        "temperature_c": _number_or_none(current.get("temperature_2m")),
        "apparent_temperature_c": _number_or_none(
            current.get("apparent_temperature")
        ),
        "relative_humidity_percent": _number_or_none(
            current.get("relative_humidity_2m")
        ),
        "weather_code": current_code,
        "weather_description": _weather_description(current_code),
        "is_day": current_is_day,
        "precipitation_mm": _number_or_none(
            current.get("precipitation")
        ),
        "rain_mm": _number_or_none(current.get("rain")),
        "snowfall_cm": _number_or_none(current.get("snowfall")),
        "cloud_cover_percent": _number_or_none(
            current.get("cloud_cover")
        ),
        "wind_speed_kmh": _number_or_none(
            current.get("wind_speed_10m")
        ),
        "wind_direction_degrees": _number_or_none(
            current.get("wind_direction_10m")
        ),
    }

    daily_results = []

    for index, date in enumerate(dates):
        code = _weather_code_or_none(
            _daily_value(daily, "weather_code", index)
        )

        daily_results.append({
            "date": date,
            "weather_code": code,
            "weather_description": _weather_description(code),
            "temperature_max_c": _number_or_none(
                _daily_value(daily, "temperature_2m_max", index)
            ),
            "temperature_min_c": _number_or_none(
                _daily_value(daily, "temperature_2m_min", index)
            ),
            "precipitation_probability_max_percent": _number_or_none(
                _daily_value(daily, "precipitation_probability_max", index)
            ),
            "precipitation_sum_mm": _number_or_none(
                _daily_value(daily, "precipitation_sum", index)
            ),
            "sunrise": _daily_value(daily, "sunrise", index),
            "sunset": _daily_value(daily, "sunset", index),
        })

    resolved_latitude = _number_or_none(payload.get("latitude"))
    resolved_longitude = _number_or_none(payload.get("longitude"))

    if resolved_latitude is None:
        resolved_latitude = float(latitude)

    if resolved_longitude is None:
        resolved_longitude = float(longitude)

    return ok({
        "latitude": resolved_latitude,
        "longitude": resolved_longitude,
        "timezone": payload.get("timezone"),
        "current": current_result,
        "daily": daily_results,
        "units": {
            "temperature": "°C",
            "wind_speed": "km/h",
            "precipitation": "mm",
            "snowfall": "cm",
        },
    })


get_weather_tool = Tool(
    name="get_weather",
    description=(
        "위도와 경도를 기준으로 Open-Meteo에서 현재 날씨와 일별 예보를 조회한다. "
        "현재 기온, 체감온도, 습도, 강수량, 바람과 일별 최고·최저 기온, "
        "강수 확률을 반환한다. 지역 좌표가 필요하면 resolve_location Tool을 "
        "먼저 사용한다."
    ),
    parameters={
        "type": "object",
        "properties": {
            "latitude": {
                "type": "number",
                "description": "위도 (-90부터 90)",
                "minimum": -90,
                "maximum": 90,
            },
            "longitude": {
                "type": "number",
                "description": "경도 (-180부터 180)",
                "minimum": -180,
                "maximum": 180,
            },
            "forecast_days": {
                "type": "integer",
                "description": "일별 예보 일수 (1부터 16, 기본값 3)",
                "minimum": 1,
                "maximum": 16,
                "default": 3,
            },
        },
        "required": ["latitude", "longitude"],
        "additionalProperties": False,
    },
    func=get_weather,
    kind="external_api",
)
