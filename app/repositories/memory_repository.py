"""세션별 대화 Memory SQLite 저장소."""

import json
import sqlite3

from datetime import datetime, timezone
from typing import Any

from .event_repository import get_database_path, init_database


def _connect() -> sqlite3.Connection:
    """기존 이벤트·플랜 DB와 동일한 SQLite 파일에 연결한다."""
    init_database()

    path = get_database_path()
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now() -> str:
    """현재 UTC 시각을 ISO 형식으로 반환한다."""
    return datetime.now(timezone.utc).isoformat()


def _validate_key(value: str, field_name: str) -> str:
    """사용자 ID와 세션 ID를 검증한다."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name}는 비어 있을 수 없습니다.")

    return value.strip()


def init_memory_table() -> None:
    """세션별 대화 Memory 테이블과 인덱스를 생성한다."""
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversation_memories (
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                context_json TEXT NOT NULL DEFAULT '{}',
                recent_summary TEXT,
                last_plan_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, session_id)
            );

            CREATE INDEX IF NOT EXISTS idx_conversation_memories_updated_at
            ON conversation_memories(updated_at);
            """
        )


def _decode_memory(row: sqlite3.Row) -> dict[str, Any]:
    """SQLite 행을 Python 딕셔너리로 변환한다."""
    memory = dict(row)
    raw_context = memory.pop("context_json", "{}")

    try:
        context = json.loads(raw_context)
    except (ValueError, TypeError):
        context = {}

    memory["context"] = context if isinstance(context, dict) else {}

    return memory


def get_memory(
    user_id: str,
    session_id: str,
) -> dict[str, Any] | None:
    """사용자와 세션에 해당하는 Memory를 조회한다."""
    user_id = _validate_key(user_id, "user_id")
    session_id = _validate_key(session_id, "session_id")

    init_memory_table()

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
                user_id,
                session_id,
                context_json,
                recent_summary,
                last_plan_id,
                created_at,
                updated_at
            FROM conversation_memories
            WHERE user_id = ? AND session_id = ?
            """,
            (user_id, session_id),
        ).fetchone()

    if row is None:
        return None

    return _decode_memory(row)


def save_memory(
    user_id: str,
    session_id: str,
    context: dict[str, Any],
    recent_summary: str | None = None,
    last_plan_id: int | None = None,
) -> dict[str, Any]:
    """세션 Memory를 저장하거나 갱신한다.

    context는 호출한 서비스에서 병합한 최신 상태를 전달한다.
    recent_summary와 last_plan_id가 None이면 기존 값을 유지한다.
    """
    user_id = _validate_key(user_id, "user_id")
    session_id = _validate_key(session_id, "session_id")

    if not isinstance(context, dict):
        raise ValueError("context는 딕셔너리여야 합니다.")

    if recent_summary is not None and not isinstance(recent_summary, str):
        raise ValueError("recent_summary는 문자열이어야 합니다.")

    if last_plan_id is not None:
        if (
            not isinstance(last_plan_id, int)
            or isinstance(last_plan_id, bool)
            or last_plan_id <= 0
        ):
            raise ValueError("last_plan_id는 양의 정수여야 합니다.")

    context_json = json.dumps(
        context,
        ensure_ascii=False,
    )
    now = _now()

    init_memory_table()

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO conversation_memories (
                user_id,
                session_id,
                context_json,
                recent_summary,
                last_plan_id,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, session_id)
            DO UPDATE SET
                context_json = excluded.context_json,
                recent_summary = COALESCE(
                    excluded.recent_summary,
                    conversation_memories.recent_summary
                ),
                last_plan_id = COALESCE(
                    excluded.last_plan_id,
                    conversation_memories.last_plan_id
                ),
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                session_id,
                context_json,
                recent_summary,
                last_plan_id,
                now,
                now,
            ),
        )

    saved_memory = get_memory(user_id, session_id)

    if saved_memory is None:
        raise RuntimeError("Memory 저장 후 조회에 실패했습니다.")

    return saved_memory
