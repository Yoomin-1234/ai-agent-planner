"""세션별 대화 맥락을 조회·병합·저장하는 서비스."""

import json
import re

from typing import Any

from ..repositories import memory_repository


# 실제 검색 조건과 대화에서 명시적으로 유지할 선호 정보
MEMORY_FIELDS = {
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
    "exclude_product_ids",
    "style",
    "fit",
    "occasion",
    "season",
    "location",
}

FIELD_LABELS = {
    "keyword": "검색 키워드",
    "category": "카테고리",
    "brand": "브랜드",
    "gender": "성별",
    "min_price": "최소 가격",
    "max_price": "최대 가격",
    "color": "색상",
    "size": "사이즈",
    "sort": "정렬 기준",
    "limit": "상품 개수",
    "style": "스타일",
    "fit": "핏",
    "occasion": "착용 상황",
    "season": "계절",
    "location": "지역",
}


def _clean_context(context: Any) -> dict[str, Any]:
    """허용된 필드만 남기고 Memory 데이터를 정리한다."""
    if not isinstance(context, dict):
        return {}

    cleaned = {}

    for key, value in context.items():
        if key not in MEMORY_FIELDS:
            continue

        if key == "exclude_product_ids":
            if isinstance(value, list):
                cleaned[key] = [
                    str(item)
                    for item in value[:50]
                    if isinstance(item, (str, int))
                    and not isinstance(item, bool)
                ]
            continue

        if value is None:
            cleaned[key] = None
        elif isinstance(value, str):
            cleaned[key] = value.strip()[:200]
        elif isinstance(value, int) and not isinstance(value, bool):
            cleaned[key] = value
        else:
            continue

    return cleaned


def parse_request_changes(message: str) -> dict[str, Any]:
    """현재 사용자 메시지에서 명시적으로 변경한 조건을 추출한다."""
    if not isinstance(message, str):
        return {}

    text = message.strip()
    changes = {}

    # 예산
    million = re.search(
        r"(\d+(?:\.\d+)?)\s*만\s*원",
        text,
    )

    won = re.search(
        r"(\d[\d,]*)\s*원",
        text,
    )

    if million:
        changes["max_price"] = int(
            float(million.group(1)) * 10000
        )
    elif won:
        changes["max_price"] = int(
            won.group(1).replace(",", "")
        )
    elif re.search(
        r"예산\s*(?:상관없이|제한 없이)|가격 제한 없이",
        text,
    ):
        changes["max_price"] = None

    # 성별
    if re.search(r"여성|여자|우먼|women", text, re.IGNORECASE):
        changes["gender"] = "women"
    elif re.search(r"남성|남자|맨즈|men", text, re.IGNORECASE):
        changes["gender"] = "men"
    elif re.search(r"성별\s*상관없이|공용으로", text):
        changes["gender"] = "all"

    # 색상
    color_aliases = [
        ("블랙", ("블랙", "검은색", "검정색", "검정", "까만색")),
        ("화이트", ("화이트", "흰색", "하얀색", "백색")),
        ("아이보리", ("아이보리",)),
        ("베이지", ("베이지",)),
        ("브라운", ("브라운", "갈색")),
        ("그레이", ("그레이", "회색")),
        ("네이비", ("네이비",)),
        ("블루", ("블루", "파란색")),
        ("레드", ("레드", "빨간색")),
        ("그린", ("그린", "초록색")),
        ("카키", ("카키",)),
        ("핑크", ("핑크", "분홍색")),
    ]

    selected_color = next(
        (
            color
            for color, aliases in color_aliases
            if any(alias in text for alias in aliases)
        ),
        None,
    )

    if selected_color:
        changes["color"] = selected_color
    elif re.search(r"색상\s*(?:상관없이|무관하게)", text):
        changes["color"] = None

    # 의류 종류 변경
    garments = [
        "니트", "코트", "셔츠", "원피스",
        "재킷", "자켓", "팬츠", "스커트",
        "패딩", "가디건", "스웨터",
    ]

    selected_garments = [
        garment for garment in garments if garment in text
    ]

    replacement_pattern = (
        r"말고|대신|바꿔|변경|교체|이번에는|이번엔"
        r"|다른 종류|새로운 종류"
    )

    if selected_garments and re.search(replacement_pattern, text):
        changes["keyword"] = selected_garments[-1]

    # 스타일
    styles = [
        "미니멀", "심플", "오버핏", "슬림핏",
        "크롭", "루즈핏", "캐주얼", "포멀",
        "스트릿", "클래식", "스포티",
    ]

    selected_styles = [
        style for style in styles if style in text
    ]

    if selected_styles:
        changes["style"] = " ".join(selected_styles)

    # 핏
    fits = [
        "오버핏", "슬림핏", "루즈핏", "레귤러핏",
        "와이드핏", "크롭핏",
    ]

    selected_fit = next(
        (fit for fit in fits if fit in text),
        None,
    )

    if selected_fit:
        changes["fit"] = selected_fit

    # 착용 상황
    occasions = [
        "출근", "데이트", "여행", "면접",
        "하객", "운동", "일상", "등교",
    ]

    selected_occasion = next(
        (occasion for occasion in occasions if occasion in text),
        None,
    )

    if selected_occasion:
        changes["occasion"] = selected_occasion

    # 계절
    seasons = ["봄", "여름", "가을", "겨울"]

    selected_season = next(
        (season for season in seasons if season in text),
        None,
    )

    if selected_season:
        changes["season"] = selected_season

    # 지역
    locations = [
        "서울", "부산", "인천", "대구", "광주",
        "대전", "울산", "세종", "수원", "성남",
        "용인", "고양", "창원", "제주",
    ]

    selected_location = next(
        (location for location in locations if location in text),
        None,
    )

    if selected_location:
        changes["location"] = selected_location

    # 브랜드
    brand_match = re.search(
        r"브랜드\s*[:=]?\s*([A-Za-z0-9가-힣]+)",
        text,
        re.IGNORECASE,
    )

    if brand_match:
        changes["brand"] = brand_match.group(1)

    # 사이즈
    size_match = re.search(
        r"사이즈\s*[:=]?\s*(XS|S|M|L|XL|XXL|XXXL)",
        text,
        re.IGNORECASE,
    )

    if size_match:
        changes["size"] = size_match.group(1).upper()

    # 정렬
    if re.search(r"저렴|싼 가격|가격 낮|가성비", text):
        changes["sort"] = "price_asc"
    elif re.search(r"신상|최신|새로운 상품", text):
        changes["sort"] = "new"

    return changes


def merge_context(
    previous_context: dict[str, Any] | None,
    request_changes: dict[str, Any] | None = None,
    search_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """이전 조건, 현재 요청, 실제 검색 조건을 병합한다.

    현재 요청에서 명시적으로 변경한 조건은 우선 적용한다.
    Tool의 기본값으로 인해 기존 조건이 사라지는 것을 방지한다.
    """
    context = _clean_context(previous_context)
    changes = _clean_context(request_changes)
    actual = _clean_context(search_context)

    # 실제 검색에 사용한 값 중 이전에 없던 조건을 보충한다.
    # 이미 저장된 조건은 현재 요청에서 명시적으로 변경한 경우에만 바꾼다.
    for key, value in actual.items():
        if key == "exclude_product_ids":
            continue

        if value is None:
            continue

        if key not in context:
            context[key] = value

    # 사용자가 명시적으로 변경한 조건을 최종 반영한다.
    context.update(changes)

    # 제외 상품 ID는 누적한다.
    exclusions = {
        str(item)
        for item in (
            list(context.get("exclude_product_ids", []))
            + list(actual.get("exclude_product_ids", []))
            + list(changes.get("exclude_product_ids", []))
        )
    }

    if exclusions:
        context["exclude_product_ids"] = sorted(exclusions)

    return _clean_context(context)


def load_turn_memory(
    user_id: str,
    session_id: str,
    user_request: str,
) -> dict[str, Any]:
    """이전 Memory를 조회하고 현재 요청의 명시적 변경을 반영한다."""
    memory = memory_repository.get_memory(user_id, session_id)

    if memory is None:
        memory = {
            "context": {},
            "recent_summary": None,
            "last_plan_id": None,
        }

    previous_context = _clean_context(memory.get("context"))

    changes = parse_request_changes(user_request)

    current_context = merge_context(
        previous_context=previous_context,
        request_changes=changes,
    )

    return {
        "context": current_context,
        "recent_summary": memory.get("recent_summary"),
        "last_plan_id": memory.get("last_plan_id"),
    }


def build_memory_prompt(
    user_request: str,
    context: dict[str, Any],
    recent_summary: str | None = None,
) -> str:
    """이전 조건을 Agent가 참고할 수 있는 프롬프트로 변환한다."""
    safe_context = _clean_context(context)

    if not safe_context and not recent_summary:
        return user_request

    lines = []

    for key, value in safe_context.items():
        if value is None or key == "exclude_product_ids":
            continue

        label = FIELD_LABELS.get(key, key)
        lines.append(f"- {label}: {value}")

    parts = [
        "[이전 대화에서 유지할 조건]",
        (
            "\n".join(lines)
            if lines
            else "- 저장된 검색 조건 없음"
        ),
        "",
        "[대화 맥락 유지 규칙]",
        "- 이전에 명시한 조건은 계속 유지한다.",
        "- 이번 요청에서 명시적으로 변경한 조건만 갱신한다.",
        "- 변경되지 않은 예산, 색상, 성별, 브랜드, 사이즈 등의 조건은 유지한다.",
        "- 상품 검색 Tool을 호출할 때 유지 중인 조건을 가능한 한 모두 반영한다.",
        "- 저장된 조건과 현재 요청이 충돌하면 현재 요청을 우선한다.",
    ]

    if recent_summary:
        parts.extend([
            "",
            "[직전 대화 요약]",
            recent_summary[:500],
        ])

    parts.extend([
        "",
        "[현재 사용자 요청]",
        user_request,
    ])

    return "\n".join(parts)


def _make_recent_summary(answer: str | None) -> str | None:
    """Agent 응답에서 최근 대화 요약으로 사용할 텍스트를 정리한다."""
    if not isinstance(answer, str) or not answer.strip():
        return None

    summary = re.sub(
        r"https?://\S+",
        "",
        answer,
    )
    summary = re.sub(r"\s+", " ", summary).strip()

    return summary[:500] if summary else None


def save_turn_memory(
    user_id: str,
    session_id: str,
    user_request: str,
    previous_context: dict[str, Any],
    answer: str,
    search_context: dict[str, Any] | None = None,
    last_plan_id: int | None = None,
) -> dict[str, Any]:
    """이번 실행에서 확인된 검색 조건과 결과 요약을 저장한다."""
    request_changes = parse_request_changes(user_request)

    context = merge_context(
        previous_context=previous_context,
        request_changes=request_changes,
        search_context=search_context,
    )

    summary = _make_recent_summary(answer)

    return memory_repository.save_memory(
        user_id=user_id,
        session_id=session_id,
        context=context,
        recent_summary=summary,
        last_plan_id=last_plan_id,
    )
