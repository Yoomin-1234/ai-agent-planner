"""공통 Tool 규격과 레지스트리.

F3001: Tool 이름, 설명, 입력 JSON Schema, 실행 함수를 한 곳에서 관리한다.
외부 API Tool과 서버 내부 Tool은 kind 값으로 구분한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

ToolKind = Literal["external_api", "local"]
ToolFunction = Callable[..., dict[str, Any]]


def ok(data: dict[str, Any]) -> dict[str, Any]:
    """성공 응답의 공통 형식."""
    return {"ok": True, "data": data}


def fail(code: str, message: str) -> dict[str, Any]:
    """실패 응답의 공통 형식. 외부 API 원문이나 인증정보는 넣지 않는다."""
    return {"ok": False, "error": {"code": code, "message": message}}


@dataclass(frozen=True, slots=True)
class Tool:
    """Agent가 사용할 Tool의 명세와 실행 함수를 보관한다."""

    name: str
    description: str
    parameters: dict[str, Any]
    func: ToolFunction
    kind: ToolKind = "external_api"

    def run(self, **kwargs: Any) -> dict[str, Any]:
        """예외를 표준 실패 응답으로 바꿔 반환한다."""
        try:
            result = self.func(**kwargs)
        except TypeError:
            return fail("BAD_ARGUMENT", "Tool 입력값이 규격과 일치하지 않습니다.")
        except Exception:
            # 비밀값이나 외부 API 응답 본문이 포함될 수 있어 원문 예외를 감춘다.
            return fail("UNKNOWN_ERROR", "Tool 실행 중 내부 오류가 발생했습니다.")

        if not isinstance(result, dict) or "ok" not in result:
            return fail("UNKNOWN_ERROR", "Tool 응답 형식이 올바르지 않습니다.")
        return result

    def public_spec(self) -> dict[str, Any]:
        """실행 함수는 제외하고 Agent/개발자에게 공개할 명세만 반환한다."""
        return {
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
            "parameters": self.parameters,
        }


TOOLS: dict[str, Tool] = {}


def register_tool(tool: Tool) -> Tool:
    """Tool을 이름으로 등록한다. 중복 이름은 조용히 덮어쓰지 않는다."""
    if tool.name in TOOLS:
        raise ValueError(f"이미 등록된 Tool 이름입니다: {tool.name}")
    TOOLS[tool.name] = tool
    return tool


def get_tool(name: str) -> Tool | None:
    return TOOLS.get(name)


def catalog() -> list[dict[str, Any]]:
    """등록된 Tool의 공개 명세 목록을 반환한다."""
    return [tool.public_spec() for tool in TOOLS.values()]


def run_tool(name: str, **kwargs: Any) -> dict[str, Any]:
    """이름으로 Tool을 실행한다."""
    tool = get_tool(name)
    if tool is None:
        return fail("NOT_FOUND", "등록되지 않은 Tool입니다.")
    return tool.run(**kwargs)
