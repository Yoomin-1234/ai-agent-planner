"""Agent 실행 및 Tool 이벤트의 SQLite 저장소."""

import json
import os
import sqlite3

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_database_path() -> Path:
    """환경변수 DATABASE_PATH 또는 기본 SQLite 경로를 반환한다."""
    configured = os.getenv("DATABASE_PATH")

    if configured:
        path = Path(configured)
        return path if path.is_absolute() else PROJECT_ROOT / path

    return PROJECT_ROOT / "data" / "app.db"


def _connect():
    path = get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_database() -> None:
    """Agent 실행 및 이벤트 테이블을 생성한다."""
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS agent_runs (
                run_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL DEFAULT 'legacy',
                user_request TEXT NOT NULL,
                status TEXT NOT NULL,
                response_text TEXT,
                error_code TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                duration_ms INTEGER
            );

            CREATE TABLE IF NOT EXISTS agent_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                session_id TEXT NOT NULL DEFAULT 'legacy',
                event_type TEXT NOT NULL,
                tool_name TEXT,
                status TEXT,
                input_data TEXT,
                output_summary TEXT,
                error_code TEXT,
                created_at TEXT NOT NULL,
                duration_ms INTEGER,
                FOREIGN KEY (run_id)
                    REFERENCES agent_runs(run_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_agent_events_run_id
            ON agent_events(run_id);

            CREATE INDEX IF NOT EXISTS idx_agent_events_created_at
            ON agent_events(created_at);
            """
        )

        # 기존 DB에도 session_id 컬럼을 안전하게 추가한다.
        run_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(agent_runs)"
            ).fetchall()
        }

        if "session_id" not in run_columns:
            conn.execute(
                "ALTER TABLE agent_runs "
                "ADD COLUMN session_id TEXT NOT NULL DEFAULT 'legacy'"
            )

        event_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(agent_events)"
            ).fetchall()
        }

        if "session_id" not in event_columns:
            conn.execute(
                "ALTER TABLE agent_events "
                "ADD COLUMN session_id TEXT NOT NULL DEFAULT 'legacy'"
            )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_runs_session_id "
            "ON agent_runs(session_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_events_session_id "
            "ON agent_events(session_id)"
        )


def create_agent_run(
    run_id: str,
    user_request: str,
    session_id: str = 'legacy',
) -> None:
    """새 Agent 실행 기록을 생성한다."""
    init_database()

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO agent_runs (
                run_id, session_id, user_request, status, started_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, session_id, user_request, "running", _now()),
        )


def update_agent_run(
    run_id: str,
    status: str,
    response_text: str | None = None,
    error_code: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """Agent 실행 결과와 종료 상태를 저장한다."""
    init_database()

    with _connect() as conn:
        conn.execute(
            """
            UPDATE agent_runs
            SET status = ?,
                response_text = ?,
                error_code = ?,
                completed_at = ?,
                duration_ms = ?
            WHERE run_id = ?
            """,
            (
                status,
                response_text,
                error_code,
                _now(),
                duration_ms,
                run_id,
            ),
        )


def insert_agent_event(
    run_id: str,
    event_type: str,
    tool_name: str | None = None,
    status: str | None = None,
    input_data: dict[str, Any] | None = None,
    output_summary: dict[str, Any] | None = None,
    error_code: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """Agent 또는 Tool 이벤트를 저장한다."""
    init_database()

    input_json = (
        json.dumps(input_data, ensure_ascii=False)
        if input_data is not None
        else None
    )

    output_json = (
        json.dumps(output_summary, ensure_ascii=False)
        if output_summary is not None
        else None
    )

    with _connect() as conn:
        run_row = conn.execute(
            "SELECT session_id FROM agent_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        session_id = run_row["session_id"] if run_row else "legacy"

        conn.execute(
            """
            INSERT INTO agent_events (
                run_id, session_id, event_type, tool_name, status,
                input_data, output_summary, error_code,
                created_at, duration_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                session_id,
                event_type,
                tool_name,
                status,
                input_json,
                output_json,
                error_code,
                _now(),
                duration_ms,
            ),
        )


def _decode_event(row: sqlite3.Row) -> dict[str, Any]:
    """JSON으로 저장된 이벤트 데이터를 복원한다."""
    item = dict(row)

    for column in ("input_data", "output_summary"):
        raw = item.get(column)

        if raw:
            try:
                item[column] = json.loads(raw)
            except (ValueError, TypeError):
                item[column] = None

    return item


def list_recent_events(
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """최근 이벤트를 조회한다."""
    init_database()

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                e.event_id,
                e.run_id,
                e.session_id,
                e.event_type,
                e.tool_name,
                e.status,
                e.input_data,
                e.output_summary,
                e.error_code,
                e.created_at,
                e.duration_ms,
                r.user_request
            FROM agent_events e
            JOIN agent_runs r ON r.run_id = e.run_id
            ORDER BY e.event_id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

    return [_decode_event(row) for row in rows]


def get_agent_run_detail(run_id: str) -> dict[str, Any] | None:
    """특정 Agent 실행과 해당 실행의 전체 이벤트를 조회한다."""
    init_database()

    with _connect() as conn:
        run = conn.execute(
            "SELECT * FROM agent_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()

        if run is None:
            return None

        events = conn.execute(
            """
            SELECT *
            FROM agent_events
            WHERE run_id = ?
            ORDER BY event_id ASC
            """,
            (run_id,),
        ).fetchall()

    return {
        "run": dict(run),
        "events": [_decode_event(row) for row in events],
    }
