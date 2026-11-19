"""코디 플랜 CRUD API."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from ..schemas.plan import (
    PlanCreate,
    PlanListResponse,
    PlanRead,
    PlanStatus,
    PlanUpdate,
)
from ..services import plan_service
from ..services.plan_service import PlanValidationError


router = APIRouter(prefix="/api/plans", tags=["plans"])


@router.post(
    "",
    response_model=PlanRead,
    status_code=status.HTTP_201_CREATED,
    summary="코디 플랜 생성",
)
def create_plan(request: PlanCreate):
    """새로운 코디 플랜을 생성한다."""
    try:
        data = request.model_dump(mode="json")
        return plan_service.create_plan(data)
    except PlanValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=PlanListResponse,
    summary="코디 플랜 목록 조회",
)
def list_plans(
    user_id: Annotated[str, Query(min_length=1, max_length=100)] = "local",
    plan_status: PlanStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """사용자별 코디 플랜 목록을 조회한다."""
    return plan_service.list_plans(
        user_id=user_id,
        status=plan_status,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{plan_id}",
    response_model=PlanRead,
    summary="코디 플랜 상세 조회",
)
def get_plan(
    plan_id: int,
    user_id: Annotated[str, Query(min_length=1, max_length=100)] = "local",
):
    """특정 코디 플랜을 조회한다."""
    plan = plan_service.get_plan(plan_id, user_id)

    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="코디 플랜을 찾을 수 없습니다.",
        )

    return plan


@router.patch(
    "/{plan_id}",
    response_model=PlanRead,
    summary="코디 플랜 수정",
)
def update_plan(
    plan_id: int,
    request: PlanUpdate,
    user_id: Annotated[str, Query(min_length=1, max_length=100)] = "local",
):
    """전달된 항목만 수정한다."""
    changes = request.model_dump(
        exclude_unset=True,
        mode="json",
    )

    try:
        plan = plan_service.update_plan(
            plan_id=plan_id,
            user_id=user_id,
            changes=changes,
        )
    except PlanValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="코디 플랜을 찾을 수 없습니다.",
        )

    return plan


@router.delete(
    "/{plan_id}",
    summary="코디 플랜 삭제",
)
def delete_plan(
    plan_id: int,
    user_id: Annotated[str, Query(min_length=1, max_length=100)] = "local",
):
    """특정 코디 플랜을 삭제한다."""
    deleted = plan_service.delete_plan(plan_id, user_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="코디 플랜을 찾을 수 없습니다.",
        )

    return {
        "deleted": True,
        "plan_id": plan_id,
    }
