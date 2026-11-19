"""Fashion Planner Agent 실행 API."""

import uuid

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from ..agents.fashion_agent import run_fashion_agent
from ..schemas.agent import AgentRunRequest
from ..schemas.replan import ReplanRequest
from ..services.replan_service import replan_existing_plan


router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/run", summary="자연어 Fashion Agent 실행")
def run_agent(request: AgentRunRequest):
    """자연어 상품 추천을 실행하고 요청 시 코디 플랜을 저장한다."""

    session_id = (
        request.session_id.strip()
        if request.session_id and request.session_id.strip()
        else str(uuid.uuid4())
    )

    result = run_fashion_agent(
        user_request=request.message,
        user_id=request.user_id,
        session_id=session_id,
    )

    if result.get("ok"):
        data = result.get("data")
        if isinstance(data, dict):
            data["session_id"] = session_id
        return result

    # 실패 응답에도 다음 요청에서 사용할 세션 ID를 포함한다.
    result["session_id"] = session_id

    error = result.get("error", {})
    code = error.get("code", "AGENT_ERROR")

    status_codes = {
        "BAD_ARGUMENT": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "NO_RESULT": status.HTTP_404_NOT_FOUND,
        "INVALID_KEY": status.HTTP_503_SERVICE_UNAVAILABLE,
        "API_LIMIT": status.HTTP_503_SERVICE_UNAVAILABLE,
        "UPSTREAM_ERROR": status.HTTP_502_BAD_GATEWAY,
        "AGENT_ERROR": status.HTTP_502_BAD_GATEWAY,
        "AGENT_LIMIT": status.HTTP_504_GATEWAY_TIMEOUT,
        "PLAN_SAVE_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
    }

    return JSONResponse(
        status_code=status_codes.get(
            code,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ),
        content=result,
    )



@router.post(
    "/replan/{plan_id}",
    summary="기존 코디 플랜 재계획",
)
def replan_agent(plan_id: int, request: ReplanRequest):
    """기존 조건을 유지하면서 사용자 변경 조건으로 상품을 재검색한다."""

    payload = request.model_dump(exclude_unset=True)
    user_id = payload.pop("user_id", "local")
    message = payload.pop("message", None)

    result = replan_existing_plan(
        plan_id=plan_id,
        user_id=user_id,
        message=message,
        changes=payload,
    )

    if result.get("ok"):
        return result

    error = result.get("error", {})
    code = error.get("code", "REPLAN_ERROR")

    status_codes = {
        "BAD_ARGUMENT": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "PLAN_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "REPLAN_LIMIT": status.HTTP_409_CONFLICT,
        "INVALID_KEY": status.HTTP_503_SERVICE_UNAVAILABLE,
        "API_LIMIT": status.HTTP_503_SERVICE_UNAVAILABLE,
        "UPSTREAM_ERROR": status.HTTP_502_BAD_GATEWAY,
        "REPLAN_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
    }

    return JSONResponse(
        status_code=status_codes.get(
            code,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ),
        content=result,
    )
