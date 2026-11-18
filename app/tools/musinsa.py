"""API.SH Musinsa 상품 검색 Tool."""
from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv

from .base import Tool, fail, ok

MUSINSA_SEARCH_URL = "https://api.api.sh/musinsa/v1/search"
REQUEST_TIMEOUT = 30


def search_products(
    keyword: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    gender: str = "all",
    min_price: int | None = None,
    max_price: int | None = None,
    color: str | None = None,
    size: str | None = None,
    sort: str = "popular",
    limit: int = 30,
    cursor: str | None = None,
) -> dict[str, Any]:
    """무신사 상품을 검색하고 Agent에 필요한 필드만 반환한다."""
    load_dotenv()

    api_key = os.getenv("APISH_KEY")
    if not api_key:
        return fail("INVALID_KEY", "APISH_KEY 환경변수가 설정되지 않았습니다.")

    # 입력 검증
    if not keyword and not category and not brand and not cursor:
        return fail("BAD_ARGUMENT", "keyword, category, brand 중 하나는 필요합니다.")

    if gender not in {"all", "men", "women"}:
        return fail("BAD_ARGUMENT", "gender는 all, men, women 중 하나여야 합니다.")

    allowed_sorts = {
        "popular", "new", "discount", "price_asc", "price_desc",
        "reviews", "sales", "sales_day", "sales_week",
        "sales_month", "sales_3months", "sales_year",
    }
    if sort not in allowed_sorts:
        return fail("BAD_ARGUMENT", "지원하지 않는 sort 값입니다.")

    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        return fail("BAD_ARGUMENT", "limit은 1부터 100 사이의 정수여야 합니다.")

    if min_price is not None and min_price < 0:
        return fail("BAD_ARGUMENT", "min_price는 0 이상이어야 합니다.")

    if max_price is not None and max_price < 0:
        return fail("BAD_ARGUMENT", "max_price는 0 이상이어야 합니다.")

    if min_price is not None and max_price is not None and min_price > max_price:
        return fail("BAD_ARGUMENT", "min_price는 max_price보다 클 수 없습니다.")

    # API.SH 문서상 다음 페이지 요청은 cursor만 전달한다.
    if cursor:
        params = {"cursor": cursor}
    else:
        params = {
            "keyword": keyword,
            "category": category,
            "brand": brand,
            "gender": gender,
            "min_price": min_price,
            "max_price": max_price,
            "color": color,
            "size": size,
            "sort": sort,
            "limit": limit,
        }
        params = {key: value for key, value in params.items() if value is not None}

    try:
        response = requests.get(
            MUSINSA_SEARCH_URL,
            params=params,
            headers={"x-api-key": api_key},
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code in (401, 403):
            return fail("INVALID_KEY", "API.SH 인증에 실패했습니다.")

        if response.status_code == 404:
            return fail("NO_RESULT", "조건에 맞는 상품을 찾지 못했습니다.")

        if response.status_code == 429:
            return fail("API_LIMIT", "API.SH 호출 한도에 도달했습니다.")

        if response.status_code >= 500:
            return fail("UPSTREAM_ERROR", "API.SH 서버에서 오류가 발생했습니다.")

        response.raise_for_status()

        payload = response.json()

    except requests.Timeout:
        return fail("UPSTREAM_ERROR", "API.SH 요청 시간이 초과되었습니다.")

    except requests.RequestException:
        return fail("UPSTREAM_ERROR", "API.SH에 연결할 수 없습니다.")

    except ValueError:
        return fail("UPSTREAM_ERROR", "API.SH 응답을 JSON으로 읽을 수 없습니다.")

    if not isinstance(payload, dict):
        return fail("UPSTREAM_ERROR", "API.SH 응답 형식이 올바르지 않습니다.")

    if payload.get("success") is False:
        return fail("UPSTREAM_ERROR", "API.SH 상품 검색에 실패했습니다.")

    raw_items = payload.get("items", [])
    if not isinstance(raw_items, list):
        return fail("UPSTREAM_ERROR", "API.SH 상품 목록 형식이 올바르지 않습니다.")

    # 이미지 URL, raw 원본 데이터는 Agent에 전달하지 않는다.
    items = []
    for product in raw_items:
        if not isinstance(product, dict):
            continue

        items.append({
            "product_id": product.get("id"),
            "name": product.get("name"),
            "brand_name": product.get("brand_name"),
            "price": product.get("price"),
            "sale_price": product.get("sale_price"),
            "coupon_price": product.get("coupon_price"),
            "discount_rate": product.get("discount_rate"),
            "gender": product.get("gender"),
            "sold_out": product.get("sold_out"),
            "product_url": product.get("url") or product.get("link"),
            "rating": product.get("rating"),
            "review_count": product.get("review_count"),
        })

    if not items:
        return fail("NO_RESULT", "조건에 맞는 상품을 찾지 못했습니다.")

    return ok({
        "items": items,
        "count": len(items),
        "next_cursor": payload.get("next_cursor"),
        "fetched_at": payload.get("fetched_at"),
        "cached": payload.get("cached"),
    })


search_products_tool = Tool(
    name="search_products",
    description="사용자의 키워드, 카테고리, 성별, 가격, 색상, 사이즈 조건으로 무신사 상품을 검색합니다.",
    kind="external_api",
    parameters={
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "검색 키워드"},
            "category": {"type": "string", "description": "무신사 카테고리 코드"},
            "brand": {"type": "string", "description": "브랜드 ID"},
            "gender": {
                "type": "string",
                "enum": ["all", "men", "women"],
                "default": "all",
            },
            "min_price": {"type": "integer", "minimum": 0},
            "max_price": {"type": "integer", "minimum": 0},
            "color": {"type": "string"},
            "size": {"type": "string"},
            "sort": {
                "type": "string",
                "enum": [
                    "popular", "new", "discount", "price_asc", "price_desc",
                    "reviews", "sales", "sales_day", "sales_week",
                    "sales_month", "sales_3months", "sales_year",
                ],
                "default": "popular",
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 30},
            "cursor": {"type": "string", "description": "이전 응답의 next_cursor"},
        },
        "additionalProperties": False,
    },
    func=search_products,
)
