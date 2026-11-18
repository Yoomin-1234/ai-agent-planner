"""Tool 카탈로그와 공통 응답 규격을 확인하는 실행 진입점.

실행:
    python -m app.tools_start
"""
from .tools.base import catalog


def main() -> None:
    print("[Tool catalog]")
    for spec in catalog():
        print(f"- {spec['name']} ({spec['kind']}): {spec['description']}")
    print("현재는 공통 규격만 준비된 상태입니다. 다음 단계에서 API Tool을 등록합니다.")


if __name__ == "__main__":
    main()
