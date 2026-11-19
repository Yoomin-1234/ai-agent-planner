"""LangGraph 기반 AI Fashion Planner Agent."""

import os
import json
import re
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
)
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


def _format_search_result(tool_result: dict, user_request: str) -> str:
    """LLM이 가격 등을 임의로 바꾸지 못하도록 API 데이터로 추천 목록을 만든다."""
    data = tool_result.get("data", {})
    items = data.get("items", [])

    if not isinstance(items, list):
        return "상품 검색 결과 형식이 올바르지 않습니다."

    max_price = _extract_max_price(user_request)
    verified_items = []

    for item in items:
        if not isinstance(item, dict):
            continue

        sale_price = item.get("sale_price")
        price = sale_price if sale_price is not None else item.get("price")

        if isinstance(price, str):
            try:
                price = int(price.replace(",", ""))
            except ValueError:
                price = None

        if max_price is not None:
            # 예산 요청에서는 가격을 확인할 수 없는 상품도 제외한다.
            if not isinstance(price, (int, float)) or price > max_price:
                continue

        verified_items.append((item, price))

    lines = ["무신사 API 검색 결과를 기준으로 정리한 상품 목록입니다."]

    if max_price is not None:
        lines.append(f"예산 조건: {max_price:,}원 이하")
        lines.append(
            f"API 검색 결과 {len(items)}개 중 예산을 확인할 수 있는 상품 "
            f"{len(verified_items)}개를 추렸습니다."
        )
    else:
        lines.append(f"검색 결과: {len(verified_items)}개")

    if not verified_items:
        lines.append("조건에 맞고 가격을 확인할 수 있는 상품을 찾지 못했습니다.")
        return "\n".join(lines)

    for index, (item, price) in enumerate(verified_items, start=1):
        name = item.get("name") or "상품명 정보 없음"
        brand = item.get("brand_name") or "브랜드 정보 없음"

        lines.append(f"\n{index}. {name}")
        lines.append(f"- 브랜드: {brand}")

        if price is not None:
            lines.append(f"- 판매가(API 기준): {price:,.0f}원")
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


def run_fashion_agent(user_request: str) -> dict:
    """사용자의 자연어 요청을 실행하고 이벤트를 기록한다."""

    if not isinstance(user_request, str) or not user_request.strip():
        return fail("BAD_ARGUMENT", "사용자 요청을 입력해야 합니다.")

    request_text = user_request.strip()

    # 실행 ID 생성 및 실행 컨텍스트 설정
    run_id = start_agent_run(request_text)
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
            config={
                "recursion_limit": 12,
            },
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
            return fail(
                "AGENT_ERROR",
                "Agent 응답을 생성하지 못했습니다.",
            )

        # 가장 마지막 상품 검색 결과를 확인한다.
        search_result = None

        for message in reversed(messages):
            if isinstance(message, ToolMessage) and message.name == "search_products":
                search_result = _decode_tool_result(message.content)
                break

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

            answer = _format_search_result(search_result, request_text)
        else:
            answer = _content_to_text(final_message.content)

        finish_agent_run(
            run_id,
            status="success",
            response_text=answer,
        )

        return ok({
            "run_id": run_id,
            "answer": answer,
            "tools_used": tools_used,
        })

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
