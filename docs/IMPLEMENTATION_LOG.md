# 구현 로그

## Milestone 01 - 프로젝트 초기화 및 F3001 공통 Tool 규격

- [x] 영화 예제와 실제 앱 코드를 분리하고 `examples/day01_fastapi/`에 원본 보존
- [x] FastAPI 앱 이름을 AI Fashion Planner로 변경
- [x] `/health` 상태 확인 API 추가
- [x] Tool 공통 성공/실패 응답 추가
- [x] Tool 이름·설명·입력 JSON Schema·종류(`external_api`/`local`) 관리
- [x] Tool 카탈로그 API 추가 (현재 등록된 외부 Tool은 다음 단계에서 추가)
- [x] Tool 단위 테스트 추가
- [x] `.env.example`, `.gitignore`, README 작성

### 로컬 검증

```bash
python -m unittest discover -s tests -v
python -m compileall -q app tests
uvicorn app.main:app --reload
```

## 다음 Milestone

F3002/F3003: API.SH Musinsa 상품 검색 및 상품 상세 Tool 구현. 실제 응답 구조를 API 키로 확인한 뒤 정규화 필드를 확정한다.
