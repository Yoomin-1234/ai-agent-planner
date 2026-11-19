"""기존 코디 플랜의 검색 조건을 보정하고 재계획한다."""

import os
import re

from pathlib import Path
from dotenv import load_dotenv

from ..services import plan_service
from ..services.event_service import (
    execute_tool_with_event,
    start_agent_run,
    activate_agent_run,
    deactivate_agent_run,
    finish_agent_run,
    record_plan_replanned,
)
from ..tools.base import fail, ok


PROJECT_ROOT = Path(__file__).resolve().parents[2]

SEARCH_FIELDS = {
    "keyword",
    "category",
    "brand",
    "gender",
    "min_price",
    "max_price",
    "color",
    "size",
    "sort",
    "limit",
}


class ReplanError(Exception):
    """재계획 처리 오류."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def get_max_replan_count() -> int:
    """환경변수의 최대 재계획 횟수를 반환한다. 기본값은 3이다."""
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

    try:
        value = int(os.getenv("REPLAN_MAX_COUNT", "3"))
        return value if value > 0 else 3
    except (TypeError, ValueError):
        return 3


def _extract_max_price(message: str):
    """자연어에서 최대 예산을 추출한다."""
    million = re.search(
        r"(\d+(?:\.\d+)?)\s*만\s*원",
        message,
    )

    if million:
        return int(float(million.group(1)) * 10000)

    won = re.search(r"(\d[\d,]*)\s*원", message)

    if won:
        return int(won.group(1).replace(",", ""))

    return None


def _parse_message_changes(message: str) -> dict:
    """자연어에서 재계획 조건 변경 사항을 추출한다."""
    changes = {}
    text = message.strip()

    price = _extract_max_price(text)
    if price is not None:
        changes["max_price"] = price

    if re.search(r"여성|여자|우먼|women", text, re.IGNORECASE):
        changes["gender"] = "women"
    elif re.search(r"남성|남자|맨즈|men", text, re.IGNORECASE):
        changes["gender"] = "men"
    elif re.search(r"성별\s*상관없이|공용으로", text):
        changes["gender"] = "all"

    colors = [
        "블랙", "화이트", "아이보리", "베이지",
        "브라운", "그레이", "네이비", "블루",
        "레드", "그린", "카키", "핑크",
    ]

    selected_color = next(
        (color for color in colors if color in text),
        None,
    )

    if selected_color:
        changes["color"] = selected_color

    garments = [
        "니트", "코트", "셔츠", "원피스",
        "재킷", "자켓", "팬츠", "스커트",
        "패딩", "가디건", "스웨터",
    ]

    selected_garments = [
        garment for garment in garments if garment in text
    ]

    if selected_garments and re.search(
        r"말고|대신|바꿔|변경|교체",
        text,
    ):
        changes["keyword"] = selected_garments[-1]
    elif not selected_garments:
        styles = [
            style for style in (
                "미니멀", "심플", "오버핏", "슬림핏",
                "크롭", "루즈핏", "캐주얼", "포멀",
            )
            if style in text
        ]

        if styles:
            changes["keyword_suffix"] = " ".join(styles)

    if re.search(r"저렴|싼 가격|가격 낮|가성비", text):
        changes["sort"] = "price_asc"
    elif re.search(r"신상|최신|새로운 상품", text):
        changes["sort"] = "new"

    if re.search(r"(?:상품|제품).*(?:빼|제외)", text):
        product_ids = re.findall(
            r"(?:상품(?:\s*ID)?\s*|상품번호\s*|ID\s*[:#]?\s*)"
            r"(\d{1,12})(?!\d)(?!\s*개)",
            text,
            flags=re.IGNORECASE,
        )
        if product_ids:
            changes["exclude_product_ids"] = product_ids

    return changes


def _fallback_context(plan: dict) -> dict:
    """이전 플랜에 검색 조건이 없을 때 기존 데이터에서 기본값을 만든다."""
    context = plan.get("search_context") or {}

    if context:
        context = dict(context)

    else:
        products = plan.get("products", [])
        first_name = (
            products[0].get("name")
            if products and isinstance(products[0], dict)
            else None
        )

        description = plan.get("description") or plan.get("title") or ""

        garments = [
            word for word in (
                "니트", "코트", "셔츠", "원피스",
                "재킷", "자켓", "팬츠", "스커트",
                "패딩", "가디건", "스웨터",
            )
            if word in description
        ]

        context = {
            "keyword": (
                garments[-1]
                if garments
                else first_name or plan.get("title", "패션")
            ),
            "gender": "all",
            "sort": "popular",
            "limit": max(3, min(len(products) or 5, 30)),
            "min_price": None,
            "max_price": plan.get("budget"),
            "category": None,
            "brand": None,
            "color": None,
            "size": None,
            "exclude_product_ids": [],
        }

    context.setdefault("gender", "all")
    context.setdefault("sort", "popular")
    context.setdefault("limit", 10)
    context.setdefault("exclude_product_ids", [])

    return context


def _merge_context(
    plan: dict,
    message: str | None,
    supplied_changes: dict,
) -> tuple[dict, dict]:
    """기존 검색 조건에 자연어 및 명시적 변경값을 병합한다."""
    context = _fallback_context(plan)

    parsed = _parse_message_changes(message or "")

    # 키워드 보조 변경
    suffix = parsed.pop("keyword_suffix", None)
    if suffix:
        current = context.get("keyword") or ""
        context["keyword"] = " ".join(
            part for part in (current, suffix) if part
        )

    new_exclusions = parsed.pop("exclude_product_ids", [])

    changes = dict(parsed)

    for key, value in supplied_changes.items():
        if key in SEARCH_FIELDS:
            changes[key] = value

    for key, value in changes.items():
        context[key] = value

    # 자연어에서 추출한 제외 상품과 명시적 제외 목록을 누적한다.
    supplied_exclusions = supplied_changes.get(
        "exclude_product_ids",
        [],
    )

    old_exclusions = context.get("exclude_product_ids", [])

    combined = {
        str(item)
        for item in [
            *old_exclusions,
            *new_exclusions,
            *supplied_exclusions,
        ]
    }

    context["exclude_product_ids"] = sorted(combined)

    if new_exclusions or supplied_exclusions:
        changes["exclude_product_ids"] = sorted(
            {
                str(value)
                for value in [*new_exclusions, *supplied_exclusions]
            }
        )

    # 숫자형 카테고리 코드만 category로 전달한다.
    category = context.get("category")

    if category and not re.fullmatch(r"\d{3}(?:\d{3})?", str(category)):
        current_keyword = context.get("keyword") or ""
        context["keyword"] = " ".join(
            part for part in (current_keyword, str(category))
            if part
        )
        context["category"] = None

    # API 검색 인자에서 지원하지 않는 값은 제거한다.
    if context.get("keyword"):
        count_match = re.search(
            r"(\d+)\s*개\s*(?:만|로|정도|추천)",
            message or "",
        )

        if count_match:
            context["limit"] = int(count_match.group(1))

    return context, changes


def _get_price(item: dict):
    value = (
        item.get("sale_price")
        if item.get("sale_price") is not None
        else item.get("price")
    )

    if isinstance(value, bool):
        return None

    if isinstance(value, str):
        try:
            return int(value.replace(",", ""))
        except ValueError:
            return None

    if isinstance(value, (int, float)):
        return int(value)

    return None


def _filter_products(
    items: list,
    context: dict,
) -> list[dict]:
    """API 결과에서 제외 상품, 예산, 성별 조건을 검증한다."""
    excluded = {
        str(value)
        for value in context.get("exclude_product_ids", [])
    }

    gender = context.get("gender", "all")
    min_price = context.get("min_price")
    max_price = context.get("max_price")
    verified = []

    for item in items:
        if not isinstance(item, dict):
            continue

        product_id = item.get("product_id")

        if product_id is None or str(product_id) in excluded:
            continue

        if item.get("sold_out") is True:
            continue

        price = _get_price(item)

        if min_price is not None:
            if price is None or price < min_price:
                continue

        if max_price is not None:
            if price is None or price > max_price:
                continue

        actual_gender = str(item.get("gender") or "").strip().lower()

        if gender == "women" and actual_gender not in {
            "여성", "w", "women", "female",
        }:
            continue

        if gender == "men" and actual_gender not in {
            "남성", "m", "men", "male",
        }:
            continue

        verified.append({
            "product_id": product_id,
            "name": item.get("name"),
            "brand_name": item.get("brand_name"),
            "sale_price": price,
            "product_url": item.get("product_url"),
        })

    return verified


def replan_existing_plan(
    plan_id: int,
    user_id: str,
    message: str | None = None,
    changes: dict | None = None,
) -> dict:
    """기존 플랜의 조건을 유지하면서 상품을 다시 검색하고 플랜을 갱신한다."""

    plan = plan_service.get_plan(plan_id, user_id)

    if plan is None:
        return fail("PLAN_NOT_FOUND", "코디 플랜을 찾을 수 없습니다.")

    max_count = get_max_replan_count()
    current_count = int(plan.get("replan_count", 0))

    if current_count >= max_count:
        return fail(
            "REPLAN_LIMIT",
            f"최대 재계획 횟수 {max_count}회에 도달했습니다.",
        )

    changes = changes or {}

    if not message and not changes:
        return fail(
            "BAD_ARGUMENT",
            "변경할 조건이나 자연어 요청을 입력해야 합니다.",
        )

    context, changed_conditions = _merge_context(
        plan,
        message,
        changes,
    )

    target_limit = int(context.get("limit") or 10)
    excluded_count = len(context.get("exclude_product_ids", []))

    # 제외 상품을 감안해 API에서 조금 더 가져온다.
    api_limit = min(100, target_limit + excluded_count)

    search_arguments = {
        key: context.get(key)
        for key in SEARCH_FIELDS
        if context.get(key) is not None
    }
    search_arguments["limit"] = api_limit

    run_text = (
        f"코디 플랜 재계획: plan_id={plan_id}, "
        f"요청={message or changed_conditions}"
    )

    run_id = start_agent_run(run_text)
    tokens = activate_agent_run(run_id)

    try:
        result = execute_tool_with_event(
            "search_products",
            **search_arguments,
        )

        if not result.get("ok"):
            error = result.get("error", {})
            code = error.get("code", "UPSTREAM_ERROR")
            message_text = error.get(
                "message",
                "재검색에 실패했습니다.",
            )

            finish_agent_run(
                run_id,
                status="failed",
                error_code=code,
            )

            return fail(code, message_text)

        items = result.get("data", {}).get("items", [])
        products = _filter_products(items, context)[:target_limit]

        next_count = current_count + 1

        if not products:
            # 검색은 성공했지만 조건에 맞는 상품이 없다.
            # 기존 상품 목록은 보존하고 시도 횟수만 증가시킨다.
            # 새 검색 결과가 없어도 제외 요청한 상품은 기존 목록에서 제거한다.
            previous_products = plan.get("products", [])
            excluded_ids = {
                str(value)
                for value in context.get("exclude_product_ids", [])
            }

            retained_products = [
                product
                for product in previous_products
                if str(product.get("product_id")) not in excluded_ids
            ]
            removed_count = len(previous_products) - len(retained_products)

            updates = {
                "replan_count": next_count,
                "search_context": context,
            }

            if len(retained_products) != len(plan.get("products", [])):
                updates["products"] = retained_products

            updated_plan = plan_service.update_plan(
                plan_id,
                user_id,
                updates,
            )

            answer = (
                "변경된 조건으로 다시 검색했지만 새 상품을 찾지 못했습니다. "
                f"제외 요청한 기존 상품 {removed_count}개를 제거했으며, "
                "나머지 상품은 유지했습니다."
            )

            record_plan_replanned(
                plan_id=plan_id,
                replan_count=next_count,
                max_replan_count=max_count,
                product_count=0,
                changed_conditions=changed_conditions,
                status="no_results",
            )

            finish_agent_run(
                run_id,
                status="success",
                response_text=answer,
            )

            return ok({
                "run_id": run_id,
                "updated": True,
                "new_products_found": False,
                "removed_product_count": removed_count,
                "answer": answer,
                "replan_count": next_count,
                "max_replan_count": max_count,
                "plan": updated_plan,
            })

        update_data = {
            "products": products,
            "replan_count": next_count,
            "search_context": context,
        }

        if "max_price" in context:
            update_data["budget"] = context.get("max_price")

        updated_plan = plan_service.update_plan(
            plan_id,
            user_id,
            update_data,
        )

        if updated_plan is None:
            finish_agent_run(
                run_id,
                status="failed",
                error_code="PLAN_NOT_FOUND",
            )
            return fail("PLAN_NOT_FOUND", "코디 플랜을 찾을 수 없습니다.")

        record_plan_replanned(
            plan_id=plan_id,
            replan_count=next_count,
            max_replan_count=max_count,
            product_count=len(products),
            changed_conditions=changed_conditions,
            status="success",
        )

        lines = [
            "기존 코디 플랜을 새로운 검색 조건으로 갱신했습니다.",
            f"플랜 ID: {plan_id}",
            f"재계획 횟수: {next_count}/{max_count}",
            f"새 상품 수: {len(products)}개",
        ]

        for index, product in enumerate(products, start=1):
            lines.append(
                f"{index}. {product.get('name')} - "
                f"{product.get('sale_price'):,}원"
            )

        answer = "\n".join(lines)

        finish_agent_run(
            run_id,
            status="success",
            response_text=answer,
        )

        return ok({
            "run_id": run_id,
            "updated": True,
            "answer": answer,
            "replan_count": next_count,
            "max_replan_count": max_count,
            "changed_conditions": changed_conditions,
            "plan": updated_plan,
        })

    except Exception:
        finish_agent_run(
            run_id,
            status="failed",
            error_code="REPLAN_ERROR",
        )

        return fail(
            "REPLAN_ERROR",
            "재계획 처리 중 오류가 발생했습니다.",
        )

    finally:
        deactivate_agent_run(tokens)
