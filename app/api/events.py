"""Agent 실행 및 Tool 이벤트 조회 API."""

from fastapi import APIRouter, HTTPException, Query

from ..repositories.event_repository import (
    get_agent_run_detail,
    init_database,
    list_recent_events,
)


router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", summary="최근 Agent 및 Tool 이벤트 조회")
def list_events(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    init_database()

    return {
        "items": list_recent_events(limit=limit, offset=offset),
        "limit": limit,
        "offset": offset,
    }


@router.get("/runs/{run_id}", summary="특정 Agent 실행 상세 조회")
def get_run_detail(run_id: str):
    init_database()

    result = get_agent_run_detail(run_id)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="해당 Agent 실행 기록을 찾을 수 없습니다.",
        )

    return result
