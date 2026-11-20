"""Kakao Local 주소 검색 Tool 테스트."""

import pytest
import requests

from app.tools import kakao_local
from app.tools.base import get_tool


class FakeResponse:
    """requests.Response를 대체하는 테스트 응답."""

    def __init__(self, status_code=200, payload=None, json_error=None):
        self.status_code = status_code
        self.payload = payload
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


@pytest.fixture
def kakao_api_key(monkeypatch):
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test-kakao-key")


def test_resolve_location_success(monkeypatch, kakao_api_key):
    """주소 검색 성공 시 좌표와 주소를 정규화한다."""
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)

        return FakeResponse(
            payload={
                "meta": {"total_count": 1},
                "documents": [
                    {
                        "address_name": "서울특별시 강남구 역삼동",
                        "address_type": "REGION",
                        "x": "127.036500",
                        "y": "37.501200",
                        "address": {
                            "region_1depth_name": "서울특별시",
                            "region_2depth_name": "강남구",
                            "region_3depth_name": "역삼동",
                        },
                        "road_address": {
                            "address_name": "서울특별시 강남구 테헤란로",
                            "zone_no": "06236",
                        },
                    }
                ],
            }
        )

    monkeypatch.setattr(kakao_local.requests, "get", fake_get)

    result = kakao_local.resolve_location(
        query="서울특별시 강남구 역삼동",
        size=5,
    )

    assert result["ok"] is True

    data = result["data"]
    location = data["results"][0]

    assert location["longitude"] == 127.0365
    assert location["latitude"] == 37.5012
    assert location["region"]["city"] == "강남구"
    assert location["road_address"] == "서울특별시 강남구 테헤란로"

    assert captured["headers"]["Authorization"] == "KakaoAK test-kakao-key"
    assert captured["params"] == {
        "query": "서울특별시 강남구 역삼동",
        "size": 5,
    }
    assert captured["timeout"] == kakao_local.REQUEST_TIMEOUT


def test_resolve_location_rejects_empty_query(kakao_api_key):
    """검색어가 비어 있으면 BAD_ARGUMENT를 반환한다."""
    result = kakao_local.resolve_location("   ")

    assert result["ok"] is False
    assert result["error"]["code"] == "BAD_ARGUMENT"


def test_resolve_location_rejects_invalid_size(kakao_api_key):
    """검색 개수가 범위를 벗어나면 BAD_ARGUMENT를 반환한다."""
    result = kakao_local.resolve_location(
        query="서울",
        size=0,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "BAD_ARGUMENT"


def test_resolve_location_requires_api_key(monkeypatch):
    """REST API 키가 없으면 INVALID_KEY를 반환한다."""
    monkeypatch.delenv("KAKAO_REST_API_KEY", raising=False)

    # 테스트 중 실제 .env 파일을 읽지 않도록 차단
    monkeypatch.setattr(
        kakao_local,
        "load_dotenv",
        lambda: None,
    )

    result = kakao_local.resolve_location("서울")

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_KEY"

def test_resolve_location_returns_no_result(monkeypatch, kakao_api_key):
    """검색 결과가 없으면 NO_RESULT를 반환한다."""
    monkeypatch.setattr(
        kakao_local.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(
            payload={"documents": []}
        ),
    )

    result = kakao_local.resolve_location("존재하지 않는 지역")

    assert result["ok"] is False
    assert result["error"]["code"] == "NO_RESULT"


@pytest.mark.parametrize("status_code", [401, 403])
def test_resolve_location_handles_auth_error(
    monkeypatch,
    kakao_api_key,
    status_code,
):
    """Kakao 인증 오류는 INVALID_KEY로 변환한다."""
    monkeypatch.setattr(
        kakao_local.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(status_code=status_code),
    )

    result = kakao_local.resolve_location("서울")

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_KEY"


def test_resolve_location_handles_rate_limit(monkeypatch, kakao_api_key):
    """호출 제한 응답은 API_LIMIT으로 변환한다."""
    monkeypatch.setattr(
        kakao_local.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(status_code=429),
    )

    result = kakao_local.resolve_location("서울")

    assert result["ok"] is False
    assert result["error"]["code"] == "API_LIMIT"


def test_resolve_location_handles_server_error(monkeypatch, kakao_api_key):
    """서버 오류는 UPSTREAM_ERROR로 변환한다."""
    monkeypatch.setattr(
        kakao_local.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(status_code=500),
    )

    result = kakao_local.resolve_location("서울")

    assert result["ok"] is False
    assert result["error"]["code"] == "UPSTREAM_ERROR"


def test_resolve_location_handles_timeout(monkeypatch, kakao_api_key):
    """요청 시간이 초과되면 UPSTREAM_ERROR를 반환한다."""

    def fake_get(*args, **kwargs):
        raise requests.Timeout()

    monkeypatch.setattr(kakao_local.requests, "get", fake_get)

    result = kakao_local.resolve_location("서울")

    assert result["ok"] is False
    assert result["error"]["code"] == "UPSTREAM_ERROR"


def test_resolve_location_handles_invalid_json(monkeypatch, kakao_api_key):
    """JSON 해석 실패는 UPSTREAM_ERROR로 처리한다."""
    monkeypatch.setattr(
        kakao_local.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(
            json_error=ValueError("invalid json")
        ),
    )

    result = kakao_local.resolve_location("서울")

    assert result["ok"] is False
    assert result["error"]["code"] == "UPSTREAM_ERROR"


def test_resolve_location_rejects_invalid_coordinates(
    monkeypatch,
    kakao_api_key,
):
    """유효한 경위도가 없는 응답은 실패 처리한다."""
    monkeypatch.setattr(
        kakao_local.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(
            payload={
                "documents": [
                    {
                        "address_name": "잘못된 좌표",
                        "x": "not-a-number",
                        "y": "37.5",
                    }
                ]
            }
        ),
    )

    result = kakao_local.resolve_location("서울")

    assert result["ok"] is False
    assert result["error"]["code"] == "UPSTREAM_ERROR"


def test_resolve_location_tool_is_registered():
    """Kakao Local Tool이 레지스트리에 등록되어야 한다."""
    # registry 모듈을 import하면 기본 Tool 등록이 수행된다.
    import app.tools.registry

    tool = get_tool("resolve_location")

    assert tool is not None
    assert tool.kind == "external_api"
    assert tool.public_spec()["parameters"]["required"] == ["query"]
