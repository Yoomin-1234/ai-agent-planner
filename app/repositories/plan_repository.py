"""코디 플랜 SQLite 저장소."""

import json
import sqlite3

from datetime import datetime, timezone
from typing import Any

from .event_repository import get_database_path, init_database


def _connect() -> sqlite3.Connection:
    """기존 이벤트 DB와 동일한 SQLite 파일에 연결한다."""
    init_database()

    path = get_database_path()
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_plan_table() -> None:
    """코디 플랜 테이블과 조회 인덱스를 생성한다."""
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL DEFAULT 'local',
                title TEXT NOT NULL,
                description TEXT,
                occasion TEXT,
                season TEXT,
                budget INTEGER CHECK (budget IS NULL OR budget >= 0),
                products_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'draft'
                    CHECK (
                        status IN (
                            'draft',
                            'planned',
                            'completed',
                            'archived'
                        )
                    ),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_plans_user_id
            ON plans(user_id);

            CREATE INDEX IF NOT EXISTS idx_plans_updated_at
            ON plans(updated_at);
            """
        )


def _decode_plan(row: sqlite3.Row) -> dict[str, Any]:
    """SQLite 행을 API 응답용 딕셔너리로 변환한다."""
    plan = dict(row)
    raw_products = plan.pop("products_json", "[]")

    try:
        plan["products"] = json.loads(raw_products)
    except (ValueError, TypeError):
        plan["products"] = []

    return plan


def create_plan(data: dict[str, Any]) -> dict[str, Any]:
    """새로운 코디 플랜을 저장하고 생성된 플랜을 반환한다."""
    init_plan_table()

    now = _now()
    products_json = json.dumps(
        data.get("products", []),
        ensure_ascii=False,
    )

    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO plans (
                user_id, title, description, occasion, season,
                budget, products_json, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("user_id", "local"),
                data["title"],
                data.get("description"),
                data.get("occasion"),
                data.get("season"),
                data.get("budget"),
                products_json,
                data.get("status", "draft"),
                now,
                now,
            ),
        )

        plan_id = cursor.lastrowid
        row = conn.execute(
            "SELECT * FROM plans WHERE id = ?",
            (plan_id,),
        ).fetchone()

    return _decode_plan(row)


def list_plans(
    user_id: str = "local",
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """사용자별 코디 플랜 목록을 페이지 단위로 조회한다."""
    init_plan_table()

    conditions = ["user_id = ?"]
    parameters: list[Any] = [user_id]

    if status is not None:
        conditions.append("status = ?")
        parameters.append(status)

    where_clause = " AND ".join(conditions)

    with _connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM plans WHERE {where_clause}",
            parameters,
        ).fetchone()[0]

        rows = conn.execute(
            f"""
            SELECT * FROM plans
            WHERE {where_clause}
            ORDER BY updated_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*parameters, limit, offset],
        ).fetchall()

    return {
        "items": [_decode_plan(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_plan(plan_id: int, user_id: str = "local") -> dict[str, Any] | None:
    """사용자 소유 범위에서 특정 플랜을 조회한다."""
    init_plan_table()

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM plans
            WHERE id = ? AND user_id = ?
            """,
            (plan_id, user_id),
        ).fetchone()

    return _decode_plan(row) if row else None


def update_plan(
    plan_id: int,
    user_id: str,
    changes: dict[str, Any],
) -> dict[str, Any] | None:
    """코디 플랜의 전달된 필드만 수정한다."""
    init_plan_table()

    allowed_fields = {
        "title",
        "description",
        "occasion",
        "season",
        "budget",
        "products",
        "status",
    }

    updates = {
        key: value
        for key, value in changes.items()
        if key in allowed_fields
    }

    if not updates:
        return get_plan(plan_id, user_id)

    if "products" in updates:
        updates["products"] = json.dumps(
            updates["products"],
            ensure_ascii=False,
        )

    updates["updated_at"] = _now()

    assignments = ", ".join(
        f"{column} = ?" for column in updates
    )
    values = list(updates.values())

    with _connect() as conn:
        cursor = conn.execute(
            f"""
            UPDATE plans
            SET {assignments}
            WHERE id = ? AND user_id = ?
            """,
            [*values, plan_id, user_id],
        )

        if cursor.rowcount == 0:
            return None

        row = conn.execute(
            """
            SELECT * FROM plans
            WHERE id = ? AND user_id = ?
            """,
            (plan_id, user_id),
        ).fetchone()

    return _decode_plan(row) if row else None


def delete_plan(plan_id: int, user_id: str = "local") -> bool:
    """사용자 소유 범위에서 코디 플랜을 삭제한다."""
    init_plan_table()

    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM plans WHERE id = ? AND user_id = ?",
            (plan_id, user_id),
        )

    return cursor.rowcount > 0
