"""Kakao Local 주소 검색 및 좌표 변환 Tool."""

import os
import math

import requests

from dotenv import load_dotenv

from .base import Tool, fail, ok


ADDRESS_SEARCH_URL = (
    "https://dapi.kakao.com/v2/local/search/address.json"
)
REQUEST_TIMEOUT = 10


def resolve_location(
    query: str,
    size: int = 10,
) -> dict:
    """주소나 지역명을 검색하여 경도·위도와 주소 정보를 반환한다."""

    if not isinstance(query, str) or not query.strip():
        return fail("BAD_ARGUMENT", "검색할 지역이나 주소를 입력해야 합니다.")

    query = query.strip()

    if len(query) > 200:
        return fail("BAD_ARGUMENT", "검색어는 200자 이하여야 합니다.")

    if (
        not isinstance(size, int)
        or isinstance(size, bool)
        or not 1 <= size <= 30
    ):
        return fail("BAD_ARGUMENT", "size는 1부터 30 사이의 정수여야 합니다.")

    load_dotenv()

    api_key = os.getenv("KAKAO_REST_API_KEY")

    if not api_key:
        return fail("INVALID_KEY", "Kakao REST API 키가 설정되지 않았습니다.")

    try:
        response = requests.get(
            ADDRESS_SEARCH_URL,
            headers={
                "Authorization": f"KakaoAK {api_key}",
            },
            params={
                "query": query,
                "size": size,
            },
            timeout=REQUEST_TIMEOUT,
        )

    except requests.Timeout:
        return fail("UPSTREAM_ERROR", "Kakao Local 요청 시간이 초과되었습니다.")

    except requests.ConnectionError:
        return fail("UPSTREAM_ERROR", "Kakao Local 서버에 연결할 수 없습니다.")

    except requests.RequestException:
        return fail("UPSTREAM_ERROR", "Kakao Local 요청 중 오류가 발생했습니다.")

    status_code = response.status_code

    if status_code in (401, 403):
        return fail("INVALID_KEY", "Kakao Local 인증에 실패했습니다.")

    if status_code == 429:
        return fail("API_LIMIT", "Kakao Local 호출 한도에 도달했습니다.")

    if status_code == 400:
        return fail("BAD_ARGUMENT", "Kakao Local 검색 인자가 올바르지 않습니다.")

    if status_code >= 500:
        return fail("UPSTREAM_ERROR", "Kakao Local 서버에서 오류가 발생했습니다.")

    if status_code >= 400:
        return fail("UPSTREAM_ERROR", "Kakao Local 요청을 처리하지 못했습니다.")

    try:
        payload = response.json()
    except (ValueError, TypeError):
        return fail("UPSTREAM_ERROR", "Kakao Local 응답을 JSON으로 읽을 수 없습니다.")

    if not isinstance(payload, dict):
        return fail("UPSTREAM_ERROR", "Kakao Local 응답 형식이 올바르지 않습니다.")

    documents = payload.get("documents", [])

    if not isinstance(documents, list):
        return fail("UPSTREAM_ERROR", "Kakao Local 주소 목록 형식이 올바르지 않습니다.")

    if not documents:
        return fail("NO_RESULT", "입력한 지역이나 주소를 찾을 수 없습니다.")

    results = []

    for document in documents:
        if not isinstance(document, dict):
            continue

        try:
            longitude = float(document.get("x"))
            latitude = float(document.get("y"))
        except (TypeError, ValueError):
            continue

        if not (
            math.isfinite(longitude)
            and math.isfinite(latitude)
            and -180 <= longitude <= 180
            and -90 <= latitude <= 90
        ):
            continue

        address = document.get("address") or {}
        road_address = document.get("road_address") or {}

        if not isinstance(address, dict):
            address = {}

        if not isinstance(road_address, dict):
            road_address = {}

        results.append({
            "address_name": document.get("address_name"),
            "address_type": document.get("address_type"),
            "longitude": longitude,
            "latitude": latitude,
            "region": {
                "province": address.get("region_1depth_name"),
                "city": address.get("region_2depth_name"),
                "district": address.get("region_3depth_name"),
            },
            "road_address": road_address.get("address_name"),
            "postal_code": road_address.get("zone_no"),
        })

    if not results:
        return fail(
            "UPSTREAM_ERROR",
            "Kakao Local 응답에서 유효한 좌표를 확인하지 못했습니다.",
        )

    return ok({
        "query": query,
        "count": len(results),
        "results": results,
    })


resolve_location_tool = Tool(
    name="resolve_location",
    description=(
        "사용자가 지정한 대한민국 지역명이나 주소를 Kakao Local로 검색하여 "
        "경도, 위도, 행정구역 및 주소 정보를 반환한다. "
        "날씨 조회를 위해 지역 좌표가 필요할 때 사용한다."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "검색할 지역명 또는 주소",
                "minLength": 1,
                "maxLength": 200,
            },
            "size": {
                "type": "integer",
                "description": "검색 결과 개수",
                "minimum": 1,
                "maximum": 30,
                "default": 10,
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    func=resolve_location,
    kind="external_api",
)
