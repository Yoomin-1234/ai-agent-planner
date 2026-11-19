"""Agent 및 Tool 실행 이벤트를 관리하는 서비스."""

import re
import time
import uuid

from contextvars import ContextVar
from typing import Any

from ..repositories import event_repository
from ..tools.registry import run_tool


_current_run_id = ContextVar("current_agent_run_id", default=None)
_current_run_started = ContextVar("current_agent_run_started", default=None)


def _redact_text(value: str, max_length: int = 5000) -> str:
    """일반적인 API 키 및 인증 문자열을 로그에서 마스킹한다."""
    value = re.sub(
        r"(?i)(api[_-]?key|authorization|password|secret)\s*[:=]\s*\S+",
        r"\1=[REDACTED]",
        value,
    )
    value = re.sub(r"(?i)Bearer\s+\S+", "Bearer [REDACTED]", value)
    value = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}", "[REDACTED]", value)

    return value[:max_length]


def _sanitize(value: Any, key: str = "") -> Any:
    """로그 저장 전에 민감한 필드를 제거하고 크기를 제한한다."""
    lowered = key.lower()

    sensitive_words = (
        "api_key",
        "authorization",
        "password",
        "secret",
        "token",
        "cursor",
    )

    if any(word in lowered for word in sensitive_words):
        return "[REDACTED]"

    if isinstance(value, dict):
        return {
            str(k): _sanitize(v, str(k))
            for k, v in list(value.items())[:30]
            if not any(
                word in str(k).lower()
                for word in sensitive_words
            )
        }

    if isinstance(value, list):
        return [_sanitize(item) for item in value[:20]]

    if isinstance(value, str):
        return _redact_text(value, max_length=500)

    if value is None or isinstance(value, (int, float, bool)):
        return value

    return str(value)[:500]


def _safe_record(function, *args, **kwargs) -> None:
    """로그 저장 실패가 Agent 실행에 영향을 주지 않도록 한다."""
    try:
        function(*args, **kwargs)
    except Exception:
        # DB 로깅 오류로 상품 검색이나 Agent 실행을 중단하지 않는다.
        pass


def _summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    """Tool 결과의 원본 전체 대신 안전한 요약만 저장한다."""
    if result.get("ok") is not True:
        error = result.get("error", {})
        return {
            "ok": False,
            "error": {
                "code": error.get("code"),
                "message": error.get("message"),
            },
        }

    data = result.get("data", {})

    if isinstance(data, dict) and isinstance(data.get("items"), list):
        items = data["items"]

        return {
            "ok": True,
            "count": data.get("count", len(items)),
            "product_ids": [
                item.get("product_id")
                for item in items[:20]
                if isinstance(item, dict)
            ],
            "cached": data.get("cached"),
        }

    if isinstance(data, dict) and "product_id" in data:
        return {
            "ok": True,
            "product_id": data.get("product_id"),
            "name": data.get("name"),
            "out_of_stock": data.get("out_of_stock"),
            "cached": data.get("cached"),
        }

    return {
        "ok": True,
        "data": _sanitize(data),
    }


def start_agent_run(
    user_request: str,
    session_id: str | None = None,
) -> str:
    """Agent 실행 ID를 생성하고 세션과 연결된 시작 이벤트를 기록한다."""
    run_id = str(uuid.uuid4())

    if not isinstance(session_id, str) or not session_id.strip():
        session_id = str(uuid.uuid4())
    else:
        session_id = session_id.strip()

    safe_request = _redact_text(user_request, max_length=2000)

    _safe_record(
        event_repository.create_agent_run,
        run_id,
        safe_request,
        session_id,
    )

    _safe_record(
        event_repository.insert_agent_event,
        run_id,
        event_type="agent.started",
        status="running",
        input_data={
            "session_id": session_id,
            "user_request": safe_request,
        },
    )

    return run_id


def activate_agent_run(run_id: str):
    """현재 실행 컨텍스트에 Agent 실행 ID를 설정한다."""
    run_token = _current_run_id.set(run_id)
    time_token = _current_run_started.set(time.perf_counter())

    return run_token, time_token


def deactivate_agent_run(tokens) -> None:
    """현재 Agent 실행 컨텍스트를 정리한다."""
    run_token, time_token = tokens
    _current_run_id.reset(run_token)
    _current_run_started.reset(time_token)


def execute_tool_with_event(name: str, **kwargs) -> dict[str, Any]:
    """Tool을 실행하고 입력값, 결과 요약, 실행 시간을 기록한다."""
    run_id = _current_run_id.get()

    if not run_id:
        return run_tool(name, **kwargs)

    safe_arguments = _sanitize(kwargs)
    started = time.perf_counter()

    _safe_record(
        event_repository.insert_agent_event,
        run_id,
        event_type="tool.started",
        tool_name=name,
        status="running",
        input_data=safe_arguments,
    )

    try:
        result = run_tool(name, **kwargs)

        if not isinstance(result, dict):
            result = {
                "ok": False,
                "error": {
                    "code": "UNKNOWN_ERROR",
                    "message": "Tool 응답 형식이 올바르지 않습니다.",
                },
            }

    except Exception:
        result = {
            "ok": False,
            "error": {
                "code": "UNKNOWN_ERROR",
                "message": "Tool 실행 중 내부 오류가 발생했습니다.",
            },
        }

    duration_ms = int((time.perf_counter() - started) * 1000)
    summary = _summarize_result(result)

    _safe_record(
        event_repository.insert_agent_event,
        run_id,
        event_type="tool.completed",
        tool_name=name,
        status="success" if result.get("ok") else "failed",
        output_summary=summary,
        error_code=(
            result.get("error", {}).get("code")
            if not result.get("ok")
            else None
        ),
        duration_ms=duration_ms,
    )

    return result


def finish_agent_run(
    run_id: str,
    status: str,
    response_text: str | None = None,
    error_code: str | None = None,
) -> None:
    """Agent 실행 종료 상태와 응답을 저장한다."""
    started = _current_run_started.get()
    duration_ms = (
        int((time.perf_counter() - started) * 1000)
        if started is not None
        else None
    )

    safe_response = (
        _redact_text(response_text, max_length=5000)
        if response_text is not None
        else None
    )

    _safe_record(
        event_repository.update_agent_run,
        run_id,
        status,
        safe_response,
        error_code,
        duration_ms,
    )

    _safe_record(
        event_repository.insert_agent_event,
        run_id,
        event_type="agent.completed" if status == "success" else "agent.failed",
        status=status,
        output_summary=(
            {"response_preview": safe_response[:500]}
            if safe_response
            else None
        ),
        error_code=error_code,
        duration_ms=duration_ms,
    )


def record_plan_saved(plan_id: int, product_count: int) -> None:
    """현재 Agent 실행에 연결된 플랜 저장 이벤트를 기록한다."""
    run_id = _current_run_id.get()

    if not run_id:
        return

    _safe_record(
        event_repository.insert_agent_event,
        run_id,
        event_type="plan.saved",
        status="success",
        output_summary={
            "plan_id": plan_id,
            "product_count": product_count,
        },
    )


def record_plan_replanned(
    plan_id: int,
    replan_count: int,
    max_replan_count: int,
    product_count: int,
    changed_conditions: dict,
    status: str = "success",
) -> None:
    """코디 플랜 재계획 이벤트를 기록한다."""
    run_id = _current_run_id.get()

    if not run_id:
        return

    _safe_record(
        event_repository.insert_agent_event,
        run_id,
        event_type="plan.replanned",
        status=status,
        output_summary={
            "plan_id": plan_id,
            "replan_count": replan_count,
            "max_replan_count": max_replan_count,
            "product_count": product_count,
            "changed_conditions": _sanitize(changed_conditions),
        },
    )
