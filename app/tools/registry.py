"""애플리케이션 시작 시 Tool 등록을 모으는 모듈."""
from .base import TOOLS, catalog, get_tool, register_tool, run_tool
from .musinsa import search_products_tool

# 기본 상품 검색 Tool 등록
register_tool(search_products_tool)

__all__ = [
    "TOOLS",
    "catalog",
    "get_tool",
    "register_tool",
    "run_tool",
]
