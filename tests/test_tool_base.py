"""F3001 공통 Tool 규격 단위 테스트."""
import unittest

from app.tools.base import Tool, catalog, fail, ok, register_tool, run_tool


class ToolBaseTests(unittest.TestCase):
    def setUp(self) -> None:
        # 테스트마다 격리된 이름으로 등록한다.
        from app.tools.base import TOOLS
        TOOLS.pop("unit_test_echo", None)

    def test_ok_and_fail_shapes(self) -> None:
        self.assertEqual(ok({"value": 1}), {"ok": True, "data": {"value": 1}})
        self.assertEqual(
            fail("BAD_ARGUMENT", "invalid"),
            {"ok": False, "error": {"code": "BAD_ARGUMENT", "message": "invalid"}},
        )

    def test_tool_run_returns_function_result(self) -> None:
        tool = Tool(
            name="unit_test_echo",
            kind="local",
            description="테스트 입력을 그대로 반환한다.",
            parameters={"type": "object", "properties": {"value": {"type": "string"}}},
            func=lambda value: ok({"value": value}),
        )
        register_tool(tool)
        self.assertEqual(tool.run(value="hello"), ok({"value": "hello"}))

    def test_bad_argument_is_normalized(self) -> None:
        tool = Tool(
            name="unit_test_echo",
            description="테스트용 Tool",
            parameters={"type": "object"},
            func=lambda required: ok({"required": required}),
        )
        self.assertEqual(
            tool.run(),
            fail("BAD_ARGUMENT", "Tool 입력값이 규격과 일치하지 않습니다."),
        )

    def test_catalog_does_not_expose_function(self) -> None:
        tool = Tool(
            name="unit_test_echo",
            kind="local",
            description="테스트용 Tool",
            parameters={"type": "object", "properties": {}},
            func=lambda: ok({}),
        )
        register_tool(tool)
        spec = next(item for item in catalog() if item["name"] == "unit_test_echo")
        self.assertEqual(spec["kind"], "local")
        self.assertNotIn("func", spec)

    def test_unknown_tool_returns_not_found(self) -> None:
        self.assertEqual(run_tool("tool_that_does_not_exist"), fail("NOT_FOUND", "등록되지 않은 Tool입니다."))


if __name__ == "__main__":
    unittest.main()
