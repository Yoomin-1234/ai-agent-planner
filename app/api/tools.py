"""개발/검증용 Tool 카탈로그 API."""
from fastapi import APIRouter

from ..tools.registry import catalog

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("", summary="등록된 Tool 카탈로그 조회")
def list_tools():
    return {"items": catalog()}
