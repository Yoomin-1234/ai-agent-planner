"""Fashion Planner Agent 실행 API."""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from ..agents.fashion_agent import run_fashion_agent
from ..schemas.agent import AgentRunRequest


router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/run", summary="자연어 Fashion Agent 실행")
def run_agent(request: AgentRunRequest):
    """자연어 상품 추천을 실행하고 요청 시 코디 플랜을 저장한다."""

    result = run_fashion_agent(
        user_request=request.message,
        user_id=request.user_id,
    )

    if result.get("ok"):
        return result

    error = result.get("error", {})
    code = error.get("code", "AGENT_ERROR")

    status_codes = {
        "BAD_ARGUMENT": status.HTTP_422_UNPROCESSABLE_ENTITY,
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
