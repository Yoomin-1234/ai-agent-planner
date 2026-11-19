"""API.SH Musinsa 상품 검색 Tool."""
from __future__ import annotations

import os
from pathlib import Path
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
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / '.env')

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

    except requests.HTTPError as exc:
        status_code = (
            exc.response.status_code
            if exc.response is not None
            else None
        )

        if status_code is not None and 400 <= status_code < 500:
            return fail(
                "BAD_ARGUMENT",
                f"API.SH 요청 인자가 올바르지 않습니다 (HTTP {status_code}).",
            )

        return fail(
            "UPSTREAM_ERROR",
            f"API.SH가 HTTP {status_code} 오류를 반환했습니다.",
        )

    except requests.ConnectionError:
        return fail(
            "UPSTREAM_ERROR",
            "API.SH 서버에 연결할 수 없습니다.",
        )

    except requests.RequestException as exc:
        return fail(
            "UPSTREAM_ERROR",
            f"API 요청 중 오류가 발생했습니다 ({type(exc).__name__}).",
        )

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


def get_product_detail(product_id: str):
    """상품 ID 또는 무신사 상품 URL로 상품 상세 정보를 조회한다."""
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / '.env')

    api_key = os.getenv("APISH_KEY")
    if not api_key:
        return fail("INVALID_KEY", "APISH_KEY가 설정되지 않았습니다.")

    if not isinstance(product_id, str) or not product_id.strip():
        return fail("BAD_ARGUMENT", "상품 ID를 입력해야 합니다.")

    product_id = product_id.strip()

    endpoint = "https://api.api.sh/musinsa/v1/product"

    try:
        response = requests.get(
            endpoint,
            headers={"x-api-key": api_key},
            params={"id": product_id},
            timeout=30,
        )

        if response.status_code in (401, 403):
            return fail("INVALID_KEY", "API.SH 인증에 실패했습니다.")

        if response.status_code == 404:
            return fail("NO_RESULT", "해당 상품을 찾을 수 없습니다.")

        if response.status_code == 429:
            return fail("API_LIMIT", "API.SH 호출 한도에 도달했습니다.")

        if response.status_code >= 500:
            return fail("UPSTREAM_ERROR", "API.SH 서버에서 오류가 발생했습니다.")

        response.raise_for_status()
        payload = response.json()

    except requests.Timeout:
        return fail("UPSTREAM_ERROR", "API.SH 요청 시간이 초과되었습니다.")

    except requests.HTTPError as exc:
        status_code = (
            exc.response.status_code
            if exc.response is not None
            else None
        )

        if status_code is not None and 400 <= status_code < 500:
            return fail(
                "BAD_ARGUMENT",
                f"API.SH 요청 인자가 올바르지 않습니다 (HTTP {status_code}).",
            )

        return fail(
            "UPSTREAM_ERROR",
            f"API.SH가 HTTP {status_code} 오류를 반환했습니다.",
        )

    except requests.ConnectionError:
        return fail(
            "UPSTREAM_ERROR",
            "API.SH 서버에 연결할 수 없습니다.",
        )

    except requests.RequestException as exc:
        return fail(
            "UPSTREAM_ERROR",
            f"API 요청 중 오류가 발생했습니다 ({type(exc).__name__}).",
        )

    except ValueError:
        return fail("UPSTREAM_ERROR", "API.SH 응답을 JSON으로 읽을 수 없습니다.")

    if not isinstance(payload, dict):
        return fail("UPSTREAM_ERROR", "API.SH 응답 형식이 올바르지 않습니다.")

    if payload.get("success") is False:
        return fail("UPSTREAM_ERROR", "API.SH 상품 상세 조회에 실패했습니다.")

    if payload.get("id") is None:
        return fail("NO_RESULT", "해당 상품을 찾을 수 없습니다.")

    # 브랜드 정보 정규화
    brand = payload.get("brand")
    if not isinstance(brand, dict):
        brand = {}

    # 카테고리 정보 정규화
    raw_category = payload.get("category")
    category = {}

    if isinstance(raw_category, dict):
        category = {
            "depth1": (
                raw_category.get("categoryDepth1Name")
                or raw_category.get("categoryDepth1Title")
            ),
            "depth2": (
                raw_category.get("categoryDepth2Name")
                or raw_category.get("categoryDepth2Title")
            ),
            "depth3": (
                raw_category.get("categoryDepth3Name")
                or raw_category.get("categoryDepth3Title")
            ),
            "depth4": (
                raw_category.get("categoryDepth4Name")
                or raw_category.get("categoryDepth4Title")
            ),
        }

    elif isinstance(raw_category, str):
        category = {"name": raw_category}

    # 소재 및 핏 정보 정규화
    materials = []
    fit = None

    raw_materials = payload.get("materials", [])

    if isinstance(raw_materials, list):
        for item in raw_materials:
            if not isinstance(item, dict):
                continue

            material_name = item.get("name")
            selected = item.get("selected")

            if isinstance(selected, list):
                selected = [
                    value for value in selected
                    if isinstance(value, (str, int, float, bool))
                ]
            elif not isinstance(selected, (str, int, float, bool)):
                selected = None

            materials.append({
                "name": material_name,
                "selected": selected,
            })

            if material_name in ("핏", "Fit", "fit"):
                fit = selected

    # 옵션 정보 정규화
    options = []
    raw_options = payload.get("options", [])

    if isinstance(raw_options, list):
        for option in raw_options:
            if not isinstance(option, dict):
                continue

            values = []
            raw_values = option.get("values", [])

            if isinstance(raw_values, list):
                for value in raw_values:
                    if isinstance(value, dict):
                        values.append({
                            "name": value.get("name"),
                            "code": value.get("code"),
                        })
                    elif isinstance(value, (str, int, float)):
                        values.append({"name": str(value)})

            options.append({
                "name": option.get("name"),
                "type": option.get("type"),
                "values": values,
            })

    # 실제 API가 제공한 variant 상태만 전달한다.
    # 옵션 목록 자체를 구매 가능 재고로 간주하지 않는다.
    variants = []
    raw_variants = payload.get("variants", [])

    if isinstance(raw_variants, list):
        for variant in raw_variants:
            if not isinstance(variant, dict):
                continue

            raw_values = variant.get("values", [])
            safe_values = []

            if isinstance(raw_values, list):
                safe_values = [
                    value for value in raw_values
                    if isinstance(value, (str, int, float, bool))
                ]

            variants.append({
                "code": variant.get("code"),
                "values": safe_values,
                "extra_price": variant.get("extra_price"),
                "active": variant.get("active"),
            })

    return ok({
        "product_id": payload.get("id"),
        "name": payload.get("name"),
        "name_en": payload.get("name_en"),
        "style_no": payload.get("style_no"),
        "brand_name": brand.get("name") or payload.get("brand_name"),
        "brand_id": brand.get("id"),
        "price": payload.get("price"),
        "list_price": payload.get("list_price"),
        "sale_price": payload.get("sale_price"),
        "coupon_price": payload.get("coupon_price"),
        "discount_rate": payload.get("discount_rate"),
        "status": payload.get("status"),
        "out_of_stock": payload.get("out_of_stock"),
        "category": category,
        "category_path": payload.get("category_path"),
        "genders": payload.get("genders"),
        "season": payload.get("season"),
        "rating": payload.get("rating"),
        "review_count": payload.get("review_count"),
        "materials": materials,
        "fit": fit,
        "options": options,
        "variants": variants,
        "product_url": payload.get("url"),
        "fetched_at": payload.get("fetched_at"),
        "cached": payload.get("cached"),
    })


get_product_detail_tool = Tool(
    name="get_product_detail",
    description="무신사 상품 ID 또는 상품 URL로 가격, 품절 여부, 카테고리, 소재, 핏, 옵션 등 상품 상세 정보를 조회합니다.",
    kind="external_api",
    parameters={
        "type": "object",
        "properties": {
            "product_id": {
                "type": "string",
                "description": "무신사 상품 ID 또는 상품 URL",
            },
        },
        "required": ["product_id"],
        "additionalProperties": False,
    },
    func=get_product_detail,
)
