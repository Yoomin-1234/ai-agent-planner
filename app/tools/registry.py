"""애플리케이션 시작 시 Tool 등록을 모으는 모듈."""

from .base import TOOLS, catalog, get_tool, register_tool, run_tool
from .musinsa import search_products_tool, get_product_detail_tool
from .kakao_local import resolve_location_tool
from .open_meteo import get_weather_tool

# 기본 Tool 등록
register_tool(search_products_tool)
register_tool(get_product_detail_tool)
register_tool(resolve_location_tool)
register_tool(get_weather_tool)

__all__ = [
    "TOOLS",
    "catalog",
    "get_tool",
    "register_tool",
    "run_tool",
]
