"""Agent와 대화 Memory 연결 테스트."""

from app.agents.fashion_agent import _get_verified_items


def test_verified_items_uses_previous_memory_budget():
    """후속 요청에도 이전 대화의 예산 조건을 적용한다."""
    tool_result = {
        "ok": True,
        "data": {
            "items": [
                {
                    "product_id": 101,
                    "name": "베이지 니트",
                    "sale_price": 90000,
                },
                {
                    "product_id": 102,
                    "name": "베이지 코트",
                    "sale_price": 150000,
                },
            ]
        },
    }

    verified = _get_verified_items(
        tool_result=tool_result,
        user_request="색상만 베이지로 바꿔 줘.",
        max_price_override=100000,
    )

    assert len(verified) == 1
    assert verified[0]["source"]["product_id"] == 101
    assert verified[0]["price"] == 90000


def test_two_turns_reuse_memory_and_preserve_budget(tmp_path, monkeypatch):
    """후속 요청에서 이전 조건을 유지하고 변경 조건만 갱신한다."""
    import json

    from langchain_core.messages import AIMessage, ToolMessage

    from app.agents import fashion_agent
    from app.repositories import event_repository, memory_repository

    db_path = tmp_path / "agent_memory_integration.db"

    monkeypatch.setattr(
        event_repository,
        "get_database_path",
        lambda: db_path,
    )
    monkeypatch.setattr(
        memory_repository,
        "get_database_path",
        lambda: db_path,
    )

    # 외부 로그 시스템은 제외하고 Agent의 실제 실행 흐름만 검증한다.
    monkeypatch.setattr(
        fashion_agent,
        "start_agent_run",
        lambda user_request, session_id=None: "test-run",
    )
    monkeypatch.setattr(
        fashion_agent,
        "activate_agent_run",
        lambda run_id: None,
    )
    monkeypatch.setattr(
        fashion_agent,
        "deactivate_agent_run",
        lambda tokens: None,
    )
    monkeypatch.setattr(
        fashion_agent,
        "finish_agent_run",
        lambda *args, **kwargs: None,
    )

    observed_prompts = []

    class FakeAgent:
        def invoke(self, payload, config=None):
            prompt = payload["messages"][0]["content"]
            observed_prompts.append(prompt)

            color = "베이지" if "베이지" in prompt else "블랙"
            call_id = f"search-{len(observed_prompts)}"

            tool_args = {
                "keyword": "미니멀 니트",
                "max_price": 100000,
                "color": color,
                "gender": "all",
                "sort": "popular",
                "limit": 10,
            }

            items = [
                {
                    "product_id": 101,
                    "name": f"{color} 니트",
                    "brand_name": "테스트 브랜드",
                    "sale_price": 90000,
                },
                {
                    "product_id": 102,
                    "name": f"{color} 코트",
                    "brand_name": "테스트 브랜드",
                    "sale_price": 150000,
                },
            ]

            return {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "search_products",
                                "args": tool_args,
                                "id": call_id,
                                "type": "tool_call",
                            }
                        ],
                    ),
                    ToolMessage(
                        content=json.dumps(
                            {
                                "ok": True,
                                "data": {
                                    "count": len(items),
                                    "items": items,
                                },
                            },
                            ensure_ascii=False,
                        ),
                        tool_call_id=call_id,
                        name="search_products",
                    ),
                    AIMessage(
                        content=f"{color} 니트 추천 결과입니다."
                    ),
                ]
            }

    monkeypatch.setattr(
        fashion_agent,
        "build_fashion_agent",
        lambda: FakeAgent(),
    )

    session_id = "integration-session-001"

    # 첫 번째 요청: 서울, 10만 원 이하, 미니멀 출근룩, 검은색
    first_result = fashion_agent.run_fashion_agent(
        user_request=(
            "서울에서 10만 원 이하로 미니멀한 출근룩 추천해 줘. "
            "검은색 위주로."
        ),
        user_id="user-1",
        session_id=session_id,
    )

    assert first_result["ok"] is True

    first_memory = memory_repository.get_memory(
        "user-1",
        session_id,
    )

    assert first_memory is not None
    assert first_memory["context"]["max_price"] == 100000
    assert first_memory["context"]["color"] == "블랙"
    assert first_memory["context"]["location"] == "서울"

    # 두 번째 요청: 색상만 베이지로 변경
    second_result = fashion_agent.run_fashion_agent(
        user_request="색상만 베이지로 바꿔 줘.",
        user_id="user-1",
        session_id=session_id,
    )

    assert second_result["ok"] is True

    second_memory = memory_repository.get_memory(
        "user-1",
        session_id,
    )

    assert second_memory is not None
    assert second_memory["context"]["color"] == "베이지"
    assert second_memory["context"]["max_price"] == 100000
    assert second_memory["context"]["location"] == "서울"
    assert second_memory["context"]["keyword"] == "미니멀 니트"

    # 두 번째 프롬프트에 기존 조건과 이전 요약이 포함되어야 한다.
    second_prompt = observed_prompts[1]

    assert "100000" in second_prompt
    assert "베이지" in second_prompt
    assert "서울" in second_prompt
    assert first_memory["recent_summary"] in second_prompt
    assert "블랙 니트" in second_prompt
    assert "90,000원" in second_prompt

    # 실제 상품 검증에도 이전 예산이 적용되어야 한다.
    second_answer = second_result["data"]["answer"]

    assert "베이지 니트" in second_answer
    assert "베이지 코트" not in second_answer
    assert "100,000원 이하" in second_answer
