"""F3010 세션 ID 연결 테스트."""

import sqlite3
import uuid

import pytest

from app.api import agent as agent_api
from app.repositories import event_repository
from app.schemas.agent import AgentRunRequest
from app.services import event_service


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """테스트마다 별도 SQLite DB를 사용한다."""
    db_path = tmp_path / "session_test.db"

    monkeypatch.setattr(
        event_repository,
        "get_database_path",
        lambda: db_path,
    )

    return db_path


def test_start_agent_run_generates_session_id(isolated_db):
    """세션 ID를 생략하면 UUID를 생성하고 로그에 저장한다."""
    run_id = event_service.start_agent_run("테스트 요청")

    detail = event_repository.get_agent_run_detail(run_id)
    session_id = detail["run"]["session_id"]

    assert session_id
    uuid.UUID(session_id)

    assert detail["events"]
    assert all(
        event["session_id"] == session_id
        for event in detail["events"]
    )


def test_start_agent_run_uses_given_session_id(isolated_db):
    """전달받은 세션 ID가 실행 기록과 이벤트에 저장된다."""
    session_id = "test-session-001"

    run_id = event_service.start_agent_run(
        "테스트 요청",
        session_id=session_id,
    )

    detail = event_repository.get_agent_run_detail(run_id)

    assert detail["run"]["session_id"] == session_id
    assert all(
        event["session_id"] == session_id
        for event in detail["events"]
    )


def test_existing_database_gets_session_columns(isolated_db):
    """기존 DB에도 session_id 컬럼을 추가한다."""
    with sqlite3.connect(isolated_db) as conn:
        conn.executescript(
            """
            CREATE TABLE agent_runs (
                run_id TEXT PRIMARY KEY,
                user_request TEXT NOT NULL,
                status TEXT NOT NULL,
                response_text TEXT,
                error_code TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                duration_ms INTEGER
            );

            CREATE TABLE agent_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                tool_name TEXT,
                status TEXT,
                input_data TEXT,
                output_summary TEXT,
                error_code TEXT,
                created_at TEXT NOT NULL,
                duration_ms INTEGER
            );
            """
        )

    event_repository.init_database()

    with sqlite3.connect(isolated_db) as conn:
        run_columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(agent_runs)"
            ).fetchall()
        }

        event_columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(agent_events)"
            ).fetchall()
        }

    assert "session_id" in run_columns
    assert "session_id" in event_columns


def test_api_generates_and_returns_session_id(monkeypatch):
    """API 요청에 세션 ID가 없으면 생성해서 응답한다."""
    captured = {}

    def fake_run_fashion_agent(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "data": {}}

    monkeypatch.setattr(
        agent_api,
        "run_fashion_agent",
        fake_run_fashion_agent,
    )

    result = agent_api.run_agent(
        AgentRunRequest(message="미니멀 출근룩 추천"),
    )

    session_id = captured["session_id"]

    assert session_id
    uuid.UUID(session_id)
    assert result["data"]["session_id"] == session_id


def test_api_reuses_existing_session_id(monkeypatch):
    """기존 세션 ID를 Agent에 전달하고 응답한다."""
    captured = {}

    def fake_run_fashion_agent(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "data": {}}

    monkeypatch.setattr(
        agent_api,
        "run_fashion_agent",
        fake_run_fashion_agent,
    )

    session_id = "existing-session-001"

    result = agent_api.run_agent(
        AgentRunRequest(
            message="베이지 색상으로 바꿔 줘",
            session_id=session_id,
        ),
    )

    assert captured["session_id"] == session_id
    assert result["data"]["session_id"] == session_id
