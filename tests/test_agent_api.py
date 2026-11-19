"""F3010 Agent API 세션 연결 테스트."""

import uuid

import pytest

from fastapi.testclient import TestClient

from app.main import app
from app.api import agent as agent_api


@pytest.fixture
def client():
    """FastAPI HTTP 테스트 클라이언트를 생성한다."""
    return TestClient(app)


def test_api_generates_session_id_when_missing(client, monkeypatch):
    """요청에 세션 ID가 없으면 UUID를 생성해 응답한다."""
    captured = {}

    def fake_run_fashion_agent(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "data": {
                "answer": "상품 추천 결과",
                "plan_saved": False,
            },
        }

    monkeypatch.setattr(
        agent_api,
        "run_fashion_agent",
        fake_run_fashion_agent,
    )

    response = client.post(
        "/api/agent/run",
        json={
            "message": "미니멀 출근룩 추천해 줘.",
            "user_id": "user-1",
        },
    )

    assert response.status_code == 200

    body = response.json()
    session_id = body["data"]["session_id"]

    assert session_id
    uuid.UUID(session_id)

    assert captured["user_request"] == "미니멀 출근룩 추천해 줘."
    assert captured["user_id"] == "user-1"
    assert captured["session_id"] == session_id


def test_api_reuses_existing_session_id(client, monkeypatch):
    """기존 세션 ID를 Agent에 전달하고 응답에도 유지한다."""
    captured = {}

    def fake_run_fashion_agent(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "data": {
                "answer": "후속 추천 결과",
                "plan_saved": False,
            },
        }

    monkeypatch.setattr(
        agent_api,
        "run_fashion_agent",
        fake_run_fashion_agent,
    )

    session_id = "existing-session-001"

    response = client.post(
        "/api/agent/run",
        json={
            "message": "색상만 베이지로 바꿔 줘.",
            "user_id": "user-1",
            "session_id": session_id,
        },
    )

    assert response.status_code == 200
    assert captured["session_id"] == session_id
    assert response.json()["data"]["session_id"] == session_id


def test_api_returns_session_id_when_agent_fails(client, monkeypatch):
    """Agent 실행 실패 시에도 세션 ID를 응답한다."""
    captured = {}

    def fake_run_fashion_agent(**kwargs):
        captured.update(kwargs)
        return {
            "ok": False,
            "error": {
                "code": "AGENT_ERROR",
                "message": "테스트용 Agent 오류",
            },
        }

    monkeypatch.setattr(
        agent_api,
        "run_fashion_agent",
        fake_run_fashion_agent,
    )

    session_id = "failed-session-001"

    response = client.post(
        "/api/agent/run",
        json={
            "message": "상품 추천해 줘.",
            "user_id": "user-1",
            "session_id": session_id,
        },
    )

    assert response.status_code == 502
    assert captured["session_id"] == session_id
    assert response.json()["session_id"] == session_id


def test_api_rejects_invalid_empty_session_id(client):
    """빈 세션 ID는 Pydantic 요청 검증에서 거부한다."""
    response = client.post(
        "/api/agent/run",
        json={
            "message": "상품 추천해 줘.",
            "user_id": "user-1",
            "session_id": "",
        },
    )

    assert response.status_code == 422
