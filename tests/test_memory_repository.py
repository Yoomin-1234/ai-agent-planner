"""세션별 대화 Memory 저장소 테스트."""

import pytest

from app.repositories import event_repository
from app.repositories import memory_repository


@pytest.fixture
def memory_db(tmp_path, monkeypatch):
    """테스트마다 독립적인 SQLite DB를 사용한다."""
    db_path = tmp_path / "memory_test.db"

    monkeypatch.setattr(
        event_repository,
        "get_database_path",
        lambda: db_path,
    )
    monkeypatch.setattr(
        memory_repository,
        "get_database_path",
        lambda: db_path,
    )

    return db_path


def test_memory_is_isolated_by_user_and_session(memory_db):
    """사용자 ID와 세션 ID에 따라 Memory가 분리되어야 한다."""
    memory_repository.save_memory(
        user_id="user-1",
        session_id="session-1",
        context={"color": "black"},
    )

    memory_repository.save_memory(
        user_id="user-1",
        session_id="session-2",
        context={"color": "beige"},
    )

    memory_repository.save_memory(
        user_id="user-2",
        session_id="session-1",
        context={"color": "white"},
    )

    first = memory_repository.get_memory("user-1", "session-1")
    second = memory_repository.get_memory("user-1", "session-2")
    third = memory_repository.get_memory("user-2", "session-1")

    assert first["context"] == {"color": "black"}
    assert second["context"] == {"color": "beige"}
    assert third["context"] == {"color": "white"}


def test_save_memory_updates_context_and_preserves_optional_values(memory_db):
    """Memory 갱신 시 context는 변경하고 생략한 선택값은 유지한다."""
    memory_repository.save_memory(
        user_id="user-1",
        session_id="session-1",
        context={
            "city": "서울",
            "budget": 100000,
            "color": "black",
        },
        recent_summary="미니멀한 출근룩을 추천함",
        last_plan_id=10,
    )

    saved = memory_repository.save_memory(
        user_id="user-1",
        session_id="session-1",
        context={
            "city": "서울",
            "budget": 100000,
            "color": "beige",
        },
    )

    assert saved["context"]["color"] == "beige"
    assert saved["context"]["city"] == "서울"
    assert saved["recent_summary"] == "미니멀한 출근룩을 추천함"
    assert saved["last_plan_id"] == 10


def test_get_memory_returns_none_when_not_found(memory_db):
    """저장된 Memory가 없으면 None을 반환한다."""
    result = memory_repository.get_memory(
        user_id="user-1",
        session_id="not-found",
    )

    assert result is None


@pytest.mark.parametrize(
    ("user_id", "session_id", "context"),
    [
        ("", "session-1", {}),
        ("user-1", "", {}),
        ("user-1", "session-1", None),
    ],
)
def test_save_memory_rejects_invalid_arguments(
    memory_db,
    user_id,
    session_id,
    context,
):
    """잘못된 ID 또는 context를 거부한다."""
    with pytest.raises(ValueError):
        memory_repository.save_memory(
            user_id=user_id,
            session_id=session_id,
            context=context,
        )
