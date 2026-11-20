"""F3010 대화 Memory 서비스 테스트."""

import pytest

from app.repositories import event_repository
from app.repositories import memory_repository
from app.services import memory_service


@pytest.fixture
def memory_db(tmp_path, monkeypatch):
    """테스트마다 독립적인 SQLite DB를 사용한다."""
    db_path = tmp_path / "memory_service_test.db"

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


def test_parse_request_changes_extracts_explicit_color():
    """색상 변경 요청만 색상 조건으로 추출한다."""
    changes = memory_service.parse_request_changes(
        "색상만 베이지로 바꿔 줘."
    )

    assert changes == {"color": "베이지"}


def test_parse_request_changes_extracts_budget_and_gender():
    """예산과 성별 조건을 추출한다."""
    changes = memory_service.parse_request_changes(
        "여성용으로 15만 원 이하 상품으로 바꿔 줘."
    )

    assert changes["gender"] == "women"
    assert changes["max_price"] == 150000


def test_merge_context_preserves_unchanged_conditions():
    """변경하지 않은 이전 조건을 그대로 보존한다."""
    previous = {
        "keyword": "미니멀 니트",
        "color": "블랙",
        "max_price": 100000,
        "gender": "women",
        "location": "서울",
    }

    changes = memory_service.parse_request_changes(
        "색상만 베이지로 바꿔 줘."
    )

    merged = memory_service.merge_context(
        previous_context=previous,
        request_changes=changes,
    )

    assert merged["color"] == "베이지"
    assert merged["keyword"] == "미니멀 니트"
    assert merged["max_price"] == 100000
    assert merged["gender"] == "women"
    assert merged["location"] == "서울"


def test_merge_context_preserves_old_values_against_tool_defaults():
    """Tool 기본값이 이전에 지정한 검색 조건을 덮어쓰지 않는다."""
    previous = {
        "gender": "women",
        "sort": "price_asc",
        "limit": 5,
        "max_price": 100000,
    }

    actual = {
        "gender": "all",
        "sort": "popular",
        "limit": 10,
        "color": "베이지",
    }

    merged = memory_service.merge_context(
        previous_context=previous,
        search_context=actual,
    )

    assert merged["gender"] == "women"
    assert merged["sort"] == "price_asc"
    assert merged["limit"] == 5
    assert merged["max_price"] == 100000
    assert merged["color"] == "베이지"


def test_merge_context_applies_explicit_new_budget():
    """새로운 예산 요청은 이전 예산을 변경한다."""
    previous = {
        "keyword": "미니멀 코트",
        "max_price": 100000,
        "color": "블랙",
    }

    changes = memory_service.parse_request_changes(
        "예산을 20만 원 이하로 변경해 줘."
    )

    merged = memory_service.merge_context(
        previous_context=previous,
        request_changes=changes,
    )

    assert merged["max_price"] == 200000
    assert merged["keyword"] == "미니멀 코트"
    assert merged["color"] == "블랙"


def test_merge_context_removes_unapproved_fields():
    """허용되지 않은 데이터는 Memory에 포함하지 않는다."""
    context = {
        "keyword": "코트",
        "api_key": "secret-value",
        "access_token": "token-value",
    }

    cleaned = memory_service.merge_context(context)

    assert cleaned == {"keyword": "코트"}


def test_build_memory_prompt_includes_previous_context():
    """Agent 프롬프트에 이전 조건과 최근 요약을 포함한다."""
    prompt = memory_service.build_memory_prompt(
        user_request="색상만 베이지로 바꿔 줘.",
        context={
            "keyword": "미니멀 니트",
            "max_price": 100000,
            "color": "베이지",
        },
        recent_summary="서울 출근룩 상품 5개를 추천함",
    )

    assert "미니멀 니트" in prompt
    assert "100000" in prompt
    assert "서울 출근룩 상품 5개를 추천함" in prompt
    assert "색상만 베이지로 바꿔 줘." in prompt


def test_load_turn_memory_returns_updated_context(memory_db):
    """저장된 Memory를 불러와 현재 요청을 반영한다."""
    memory_repository.save_memory(
        user_id="user-1",
        session_id="session-1",
        context={
            "keyword": "미니멀 니트",
            "color": "블랙",
            "max_price": 100000,
        },
        recent_summary="기존 상품 추천 완료",
    )

    memory = memory_service.load_turn_memory(
        user_id="user-1",
        session_id="session-1",
        user_request="색상만 베이지로 변경해 줘.",
    )

    assert memory["context"]["color"] == "베이지"
    assert memory["context"]["keyword"] == "미니멀 니트"
    assert memory["context"]["max_price"] == 100000
    assert memory["recent_summary"] == "기존 상품 추천 완료"


def test_save_turn_memory_persists_updated_context(memory_db):
    """실행 결과와 실제 검색 조건을 Memory에 저장한다."""
    saved = memory_service.save_turn_memory(
        user_id="user-1",
        session_id="session-1",
        user_request="색상만 베이지로 바꿔 줘.",
        previous_context={
            "keyword": "미니멀 니트",
            "max_price": 100000,
            "color": "블랙",
        },
        search_context={
            "keyword": "미니멀 니트",
            "color": "베이지",
            "gender": "all",
        },
        answer="베이지 미니멀 니트 상품을 추천했습니다.",
    )

    assert saved["context"]["color"] == "베이지"
    assert saved["context"]["max_price"] == 100000
    assert saved["recent_summary"] == (
        "베이지 미니멀 니트 상품을 추천했습니다."
    )


def test_memory_service_keeps_sessions_isolated(memory_db):
    """서로 다른 세션의 대화 맥락이 섞이지 않는다."""
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

    first = memory_service.load_turn_memory(
        "user-1",
        "session-1",
        "추천 결과를 더 보여 줘.",
    )
    second = memory_service.load_turn_memory(
        "user-1",
        "session-2",
        "추천 결과를 더 보여 줘.",
    )

    assert first["context"]["color"] == "black"
    assert second["context"]["color"] == "beige"


def test_actual_search_context_does_not_overwrite_existing_conditions():
    """Tool 검색 인자가 명시적인 요청 없이 기존 조건을 덮어쓰지 않는다."""
    previous = {
        "max_price": 100000,
        "color": "블랙",
        "gender": "women",
    }

    actual = {
        "max_price": 200000,
        "color": "베이지",
        "gender": "all",
    }

    merged = memory_service.merge_context(
        previous_context=previous,
        search_context=actual,
    )

    assert merged["max_price"] == 100000
    assert merged["color"] == "블랙"
    assert merged["gender"] == "women"
