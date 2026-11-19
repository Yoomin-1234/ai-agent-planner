"""LangGraph 기반 AI Fashion Planner Agent."""

import os
import json
import re
import uuid
from typing import Literal

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from ..services.event_service import (
    execute_tool_with_event,
    start_agent_run,
    activate_agent_run,
    deactivate_agent_run,
    finish_agent_run,
    record_plan_saved,
)
from ..services import plan_service
from ..tools.base import fail, ok


SYSTEM_PROMPT = """
너는 AI Fashion Planner의 패션 상품 탐색 전문 Agent다.

사용자의 요청을 분석하고, 필요한 경우 등록된 Musinsa Tool을 사용한다.

[사용 가능한 Tool]
1. search_products
   - 키워드, 카테고리, 브랜드, 성별, 가격, 색상, 사이즈 조건으로 상품 검색
2. get_product_detail
   - 상품 ID로 특정 상품의 상세 정보 조회

[Tool 사용 규칙]
- 새로운 상품을 찾는 요청에는 search_products를 사용한다.
- 특정 상품의 소재, 핏, 옵션, 상세 가격 등을 확인하려면
  get_product_detail을 사용한다.
- 검색 결과에 상품 ID가 있으면 해당 ID를 상세 조회에 활용할 수 있다.
- 사용자의 조건을 가능한 한 검색 인자로 변환한다.
- 니트, 코트, 셔츠, 원피스 등 자연어 의류 종류는 keyword에 포함한다.
- category에는 숫자형 무신사 카테고리 코드만 전달한다.
- 카테고리 코드를 모르면 category를 생략한다.
- 예를 들어 미니멀한 니트 검색은 keyword="미니멀 니트"로 전달한다.
- 추천할 상품 개수는 limit으로 전달하고 keyword에 숫자를 포함하지 않는다.
- 검색 키워드에는 의류 종류, 스타일, 색상 등 검색에 필요한 단어만 포함한다.
- 상품 고유 모델 번호가 명시된 경우에만 해당 번호를 keyword에 포함한다.
- 조건이 불명확하면 임의로 확정하지 않는다.

[정확성 규칙]
- Tool 응답에 없는 상품 정보를 만들어내지 않는다.
- 소재나 핏 정보가 없으면 확인되지 않았다고 설명한다.
- 옵션 목록만으로 실제 구매 가능 재고나 사이즈별 재고를 확정하지 않는다.
- 품절 여부는 API 응답의 상태를 기준으로 설명한다.
- 가격, 할인율, 브랜드, 상품명은 API 응답을 기준으로 설명한다.
- Musinsa 상품 이미지나 원본 리뷰 내용을 출력하지 않는다.
- 상품 URL이 제공된 경우 원본 상품 페이지 링크를 안내할 수 있다.

[응답 규칙]
- 한국어로 답변한다.
- 핵심 상품 정보와 추천 이유를 이해하기 쉽게 정리한다.
- 검색 결과가 없으면 없다고 솔직하게 답변한다.
- 확인되지 않은 정보를 추측해서 채우지 않는다.
"""


@tool("search_products")
def search_products_agent_tool(
    keyword: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    gender: Literal["all", "men", "women"] = "all",
    min_price: int | None = None,
    max_price: int | None = None,
    color: str | None = None,
    size: str | None = None,
    sort: Literal[
        "popular",
        "new",
        "discount",
        "price_asc",
        "price_desc",
        "reviews",
        "sales",
        "sales_day",
        "sales_week",
        "sales_month",
        "sales_3months",
        "sales_year",
    ] = "popular",
    limit: int = 10,
    cursor: str | None = None,
) -> dict:
    """무신사에서 조건에 맞는 패션 상품을 검색한다."""

    # 자연어 카테고리명을 API 검색 키워드로 변환한다.
    if category:
        category_parts = [
            part.strip() for part in category.split(",")
        ]

        is_category_code = bool(category_parts) and all(
            re.fullmatch(r"\d{3}(?:\d{3})?", part)
            for part in category_parts
        )

        if not is_category_code:
            keyword_parts = []

            for part in (keyword, category):
                if part and part.strip() and part.strip() not in keyword_parts:
                    keyword_parts.append(part.strip())

            keyword = " ".join(keyword_parts)
            category = None

    arguments = {
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
        "cursor": cursor,
    }

    # 입력되지 않은 선택 인자는 기존 Tool에 전달하지 않는다.
    arguments = {
        key: value
        for key, value in arguments.items()
        if value is not None
    }

    return execute_tool_with_event("search_products", **arguments)


@tool("get_product_detail")
def get_product_detail_agent_tool(product_id: str) -> dict:
    """무신사 상품 ID를 이용해 상품 상세 정보를 조회한다."""

    return execute_tool_with_event(
        "get_product_detail",
        product_id=product_id,
    )


def build_fashion_agent():
    """LLM과 Musinsa Tools를 연결한 LangGraph Agent를 생성한다."""

    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")

    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    base_url = os.getenv("OPENAI_BASE_URL") or None

    model = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
        timeout=60,
        max_retries=2,
    )

    agent = create_agent(
        model=model,
        tools=[
            search_products_agent_tool,
            get_product_detail_agent_tool,
        ],
        system_prompt=SYSTEM_PROMPT,
        name="fashion_planner",
    )

    return agent


def _content_to_text(content) -> str:
    """AIMessage의 content를 문자열로 변환한다."""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []

        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))

        return "\n".join(parts)

    return str(content)



def _decode_tool_result(content):
    """ToolMessage의 JSON 결과를 Python 객체로 변환한다."""
    if isinstance(content, dict):
        return content

    if isinstance(content, str):
        try:
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else None
        except (ValueError, TypeError):
            return None

    return None


def _extract_max_price(user_request: str):
    """사용자 요청에서 '5만 원 이하', '50000원 이하' 같은 예산을 추출한다."""
    million_match = re.search(
        r"(\d+(?:\.\d+)?)\s*만\s*원",
        user_request,
    )

    if million_match:
        return int(float(million_match.group(1)) * 10000)

    won_match = re.search(
        r"(\d[\d,]*)\s*원",
        user_request,
    )

    if won_match:
        return int(won_match.group(1).replace(",", ""))

    return None



def _get_verified_items(tool_result: dict, user_request: str):
    """API 원본 결과에서 예산을 충족하고 상품 ID가 확인된 항목만 추출한다."""
    data = tool_result.get("data", {})
    items = data.get("items", [])

    if not isinstance(items, list):
        return []

    max_price = _extract_max_price(user_request)
    verified = []

    for item in items:
        if not isinstance(item, dict):
            continue

        product_id = item.get("product_id")

        if not isinstance(product_id, (int, str)) or not str(product_id).strip():
            continue

        price = (
            item.get("sale_price")
            if item.get("sale_price") is not None
            else item.get("price")
        )

        if isinstance(price, bool):
            price = None
        elif isinstance(price, str):
            try:
                price = int(price.replace(",", ""))
            except ValueError:
                price = None
        elif isinstance(price, (int, float)):
            price = int(price)
        else:
            price = None

        # 예산 조건이 있으면 가격 미확인 상품과 예산 초과 상품을 제외한다.
        if max_price is not None:
            if price is None or price > max_price:
                continue

        verified.append({
            "source": item,
            "price": price,
        })

    return verified


def _format_search_result(
    tool_result: dict,
    user_request: str,
    verified_items: list[dict] | None = None,
) -> str:
    """API에서 검증한 상품 정보로 추천 응답을 생성한다."""
    raw_items = tool_result.get("data", {}).get("items", [])

    if not isinstance(raw_items, list):
        return "상품 검색 결과 형식이 올바르지 않습니다."

    if verified_items is None:
        verified_items = _get_verified_items(tool_result, user_request)

    max_price = _extract_max_price(user_request)

    lines = ["무신사 API 검색 결과를 기준으로 정리한 상품 목록입니다."]

    if max_price is not None:
        lines.append(f"예산 조건: {max_price:,}원 이하")
        lines.append(
            f"API 검색 결과 {len(raw_items)}개 중 조건을 통과한 상품 "
            f"{len(verified_items)}개를 추렸습니다."
        )
    else:
        lines.append(f"검색 결과: {len(verified_items)}개")

    if not verified_items:
        lines.append("조건에 맞는 상품을 찾지 못했습니다.")
        return "\n".join(lines)

    for index, entry in enumerate(verified_items, start=1):
        item = entry["source"]
        price = entry["price"]

        lines.append(f"\n{index}. {item.get('name') or '상품명 정보 없음'}")
        lines.append(f"- 브랜드: {item.get('brand_name') or '브랜드 정보 없음'}")

        if price is not None:
            lines.append(f"- 판매가(API 기준): {price:,}원")
        else:
            lines.append("- 판매가: 정보 없음")

        discount = item.get("discount_rate")
        if isinstance(discount, (int, float)):
            lines.append(f"- 할인율: {discount}%")

        rating = item.get("rating")
        review_count = item.get("review_count")

        if rating is not None:
            lines.append(f"- 평점 지표(API 원본): {rating}")

        if review_count is not None:
            lines.append(f"- 리뷰 수: {review_count}개")

        gender = item.get("gender")
        if gender:
            lines.append(f"- 성별 구분(API 원본): {gender}")

        product_url = item.get("product_url")
        if (
            isinstance(product_url, str)
            and product_url.startswith("https://www.musinsa.com/products/")
        ):
            lines.append(f"- 상품 링크: {product_url}")

    return "\n".join(lines)


def _should_save_plan(user_request: str) -> bool:
    """사용자가 코디 플랜 저장을 명시적으로 요청했는지 판단한다."""
    text = user_request.strip()

    # 명시적인 저장 거부나 취소 표현이 있으면 저장하지 않는다.
    negative_patterns = [
        r"저장.{0,8}(?:하지\s*마|하지\s*말|안\s*해|필요\s*없)",
        r"플랜.{0,8}(?:만들|생성|저장).{0,8}(?:하지\s*마|하지\s*말|안\s*해)",
    ]

    if any(re.search(pattern, text) for pattern in negative_patterns):
        return False

    positive_patterns = [
        r"저장\s*(?:해\s*줘|해\s*주세요|해줘|해주세요|해주라|해)",
        r"플랜(?:으로|에|을)?\s*(?:저장|만들|생성|추가|넣)",
        r"코디\s*플랜.{0,8}(?:저장|만들|생성|추가|넣)",
        r"계획(?:으로|에)?\s*(?:저장|추가|넣)",
    ]

    return any(re.search(pattern, text) for pattern in positive_patterns)


def _extract_plan_metadata(user_request: str) -> dict:
    """자연어 요청에서 플랜 제목, 계절, 착용 목적, 예산을 추출한다."""

    seasons = ["봄", "여름", "가을", "겨울"]
    occasions = [
        "출근", "데이트", "면접", "여행",
        "운동", "일상", "하객", "등교", "캠퍼스",
    ]
    categories = [
        "니트", "코트", "셔츠", "원피스",
        "재킷", "자켓", "팬츠", "스커트",
        "패딩", "가디건", "스웨터",
    ]

    season = next(
        (value for value in seasons if value in user_request),
        None,
    )

    occasion = next(
        (value for value in occasions if value in user_request),
        None,
    )

    category = next(
        (value for value in categories if value in user_request),
        None,
    )

    if season and occasion:
        title = f"{season} {occasion} 코디"
    elif season:
        title = f"{season} 코디 플랜"
    elif occasion:
        title = f"{occasion} 코디"
    elif category:
        title = f"{category} 추천 코디"
    else:
        title = "맞춤 코디 플랜"

    return {
        "title": title,
        "description": user_request[:2000],
        "occasion": occasion,
        "season": season,
        "budget": _extract_max_price(user_request),
    }



def _extract_search_context(messages, user_request: str) -> dict:
    """최초 상품 검색 Tool 호출 인자를 재계획용으로 저장한다."""
    allowed = {
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

    for message in reversed(messages):
        if not isinstance(message, AIMessage):
            continue

        for call in reversed(message.tool_calls):
            if call.get("name") != "search_products":
                continue

            args = call.get("args", {})
            if not isinstance(args, dict):
                continue

            context = {
                key: args[key]
                for key in allowed
                if key in args
            }

            category = context.get("category")
            if category and not re.fullmatch(
                r"\d{3}(?:\d{3})?",
                str(category),
            ):
                keyword_parts = [
                    part for part in (
                        context.get("keyword"),
                        str(category),
                    )
                    if part
                ]
                context["keyword"] = " ".join(keyword_parts)
                context["category"] = None

            # 요청 개수가 검색어 뒤에 잘못 붙은 경우 제거한다.
            count_match = re.search(r"(\d+)\s*개", user_request)
            keyword = context.get("keyword")

            if count_match and isinstance(keyword, str):
                keyword = re.sub(r"\s+\d{1,2}$", "", keyword).strip()
                context["keyword"] = keyword or None

            context.setdefault("gender", "all")
            context.setdefault("sort", "popular")
            context.setdefault("limit", 10)
            context["exclude_product_ids"] = []

            return context

    return {}


def _build_plan_products(verified_items: list[dict]) -> list[dict]:
    """검증된 API 상품 데이터만 플랜 저장 형식으로 변환한다."""
    products = []

    for entry in verified_items:
        item = entry["source"]
        product_url = item.get("product_url")

        if not (
            isinstance(product_url, str)
            and product_url.startswith("https://www.musinsa.com/products/")
        ):
            product_url = None

        products.append({
            "product_id": item["product_id"],
            "name": item.get("name"),
            "brand_name": item.get("brand_name"),
            "sale_price": entry["price"],
            "product_url": product_url,
        })

    return products

def run_fashion_agent(
    user_request: str,
    user_id: str = "local",
    session_id: str | None = None,
) -> dict:
    """자연어 상품 추천을 실행하고, 명시적인 요청이 있으면 플랜으로 저장한다."""

    if not isinstance(user_request, str) or not user_request.strip():
        return fail("BAD_ARGUMENT", "사용자 요청을 입력해야 합니다.")

    if not isinstance(user_id, str) or not user_id.strip():
        return fail("BAD_ARGUMENT", "user_id는 비어 있을 수 없습니다.")

    if session_id is None:
        session_id = str(uuid.uuid4())
    elif not isinstance(session_id, str) or not session_id.strip():
        return fail("BAD_ARGUMENT", "session_id는 비어 있을 수 없습니다.")
    else:
        session_id = session_id.strip()

    request_text = user_request.strip()
    user_id = user_id.strip()
    save_requested = _should_save_plan(request_text)

    run_id = start_agent_run(request_text, session_id=session_id)
    context_tokens = activate_agent_run(run_id)

    try:
        agent = build_fashion_agent()

        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": request_text,
                    }
                ]
            },
            config={"recursion_limit": 12},
        )

        messages = result.get("messages", [])

        final_message = next(
            (
                message
                for message in reversed(messages)
                if isinstance(message, AIMessage)
            ),
            None,
        )

        tools_used = []

        for message in messages:
            if isinstance(message, AIMessage):
                for tool_call in message.tool_calls:
                    tool_name = tool_call.get("name")

                    if tool_name and tool_name not in tools_used:
                        tools_used.append(tool_name)

        if final_message is None:
            finish_agent_run(
                run_id,
                status="failed",
                error_code="AGENT_ERROR",
            )
            return fail("AGENT_ERROR", "Agent 응답을 생성하지 못했습니다.")

        # 가장 마지막 검색 결과를 가져온다.
        search_result = None

        for message in reversed(messages):
            if isinstance(message, ToolMessage) and message.name == "search_products":
                search_result = _decode_tool_result(message.content)
                break

        plan = None
        plan_saved = False

        if search_result is not None:
            if search_result.get("ok") is False:
                error = search_result.get("error", {})
                error_code = error.get("code", "UPSTREAM_ERROR")
                error_message = error.get(
                    "message",
                    "상품 검색에 실패했습니다.",
                )

                finish_agent_run(
                    run_id,
                    status="failed",
                    error_code=error_code,
                )
                return fail(error_code, error_message)

            verified_items = _get_verified_items(
                search_result,
                request_text,
            )

            answer = _format_search_result(
                search_result,
                request_text,
                verified_items,
            )

            if save_requested:
                if not verified_items:
                    answer += (
                        "\n\n조건을 충족하는 상품이 없어 "
                        "코디 플랜은 저장하지 않았습니다."
                    )
                else:
                    metadata = _extract_plan_metadata(request_text)
                    products = _build_plan_products(verified_items)

                    try:
                        plan = plan_service.create_plan({
                            "user_id": user_id,
                            **metadata,
                            "products": products,
                            "search_context": _extract_search_context(messages, request_text),
                            "status": "draft",
                        })
                    except Exception:
                        finish_agent_run(
                            run_id,
                            status="failed",
                            error_code="PLAN_SAVE_ERROR",
                        )
                        return fail(
                            "PLAN_SAVE_ERROR",
                            "상품 검색은 성공했지만 코디 플랜 저장에 실패했습니다.",
                        )

                    plan_saved = True
                    record_plan_saved(
                        plan_id=plan["id"],
                        product_count=len(products),
                    )

                    answer += (
                        "\n\n코디 플랜 저장이 완료되었습니다."
                        f"\n- 플랜 ID: {plan['id']}"
                        f"\n- 플랜 제목: {plan['title']}"
                        f"\n- 저장 상품 수: {len(products)}개"
                    )

        else:
            answer = _content_to_text(final_message.content)

            if save_requested:
                answer += (
                    "\n\n상품 검색 결과가 없어 "
                    "코디 플랜을 저장하지 않았습니다."
                )

        finish_agent_run(
            run_id,
            status="success",
            response_text=answer,
        )

        response_data = {
            "run_id": run_id,
            "session_id": session_id,
            "answer": answer,
            "tools_used": tools_used,
            "plan_saved": plan_saved,
        }

        if plan is not None:
            response_data["plan"] = plan

        return ok(response_data)

    except Exception as exc:
        if exc.__class__.__name__ == "GraphRecursionError":
            error_code = "AGENT_LIMIT"
            error_message = "Agent 실행 단계 제한에 도달했습니다."
        else:
            error_code = "AGENT_ERROR"
            error_message = (
                "Agent 실행에 실패했습니다. API 키, 모델 이름, "
                "API 주소 및 모델의 Tool Calling 지원 여부를 확인해 주세요."
            )

        finish_agent_run(
            run_id,
            status="failed",
            error_code=error_code,
        )

        return fail(error_code, error_message)

    finally:
        deactivate_agent_run(context_tokens)
