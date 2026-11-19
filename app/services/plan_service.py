"""코디 플랜 비즈니스 로직."""

from typing import Any

from ..repositories import plan_repository


class PlanValidationError(ValueError):
    """플랜 입력값 검증 오류."""


def create_plan(data: dict[str, Any]) -> dict[str, Any]:
    """코디 플랜을 생성한다."""
    payload = dict(data)

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        raise PlanValidationError("플랜 제목은 필수입니다.")

    payload["title"] = title.strip()

    user_id = payload.get("user_id", "local")
    if not isinstance(user_id, str) or not user_id.strip():
        raise PlanValidationError("user_id는 비어 있을 수 없습니다.")

    payload["user_id"] = user_id.strip()

    return plan_repository.create_plan(payload)


def list_plans(
    user_id: str = "local",
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """코디 플랜 목록을 조회한다."""
    return plan_repository.list_plans(
        user_id=user_id,
        status=status,
        limit=limit,
        offset=offset,
    )


def get_plan(plan_id: int, user_id: str = "local"):
    """코디 플랜 상세 정보를 조회한다."""
    return plan_repository.get_plan(plan_id, user_id)


def update_plan(
    plan_id: int,
    user_id: str,
    changes: dict[str, Any],
):
    """코디 플랜을 부분 수정한다."""
    if not changes:
        raise PlanValidationError("수정할 항목을 하나 이상 입력해야 합니다.")

    updates = dict(changes)

    if "title" in updates:
        title = updates["title"]

        if not isinstance(title, str) or not title.strip():
            raise PlanValidationError("플랜 제목은 비어 있을 수 없습니다.")

        updates["title"] = title.strip()

    if "products" in updates and updates["products"] is None:
        raise PlanValidationError(
            "상품 목록을 비우려면 빈 배열을 전달해야 합니다."
        )

    return plan_repository.update_plan(
        plan_id=plan_id,
        user_id=user_id,
        changes=updates,
    )


def delete_plan(plan_id: int, user_id: str = "local") -> bool:
    """코디 플랜을 삭제한다."""
    return plan_repository.delete_plan(plan_id, user_id)
