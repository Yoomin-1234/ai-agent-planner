# AI 패션 통합 플래너

자연어로 입력한 상황·예산·스타일·상품 조건을 바탕으로 패션 상품 후보와 코디 조합을 제안하고, 계획을 저장·관리하는 AI Agent 프로젝트입니다.

## 프로젝트 원칙

- 일반 상품 추천에서는 API.SH Musinsa 상품 API만 기본 경로로 사용합니다.
- 사용자가 날씨 고려를 명시한 경우에만 Kakao Local로 좌표를 확인하고 Open-Meteo 예보를 조회합니다.
- 날짜·지역이 없는 날씨 요청은 해당 정보만 사용자에게 질문한 뒤 조회합니다.
- 예산·품절·사이즈는 가능한 한 코드로 검증하며, 확인할 수 없는 정보는 추정하지 않습니다.
- 무신사 상품 이미지, 상세 설명 HTML, 리뷰 원문은 직접 표시하지 않습니다. 상품의 사실 정보와 검증된 원본 상품 링크를 사용합니다.
- API 키는 `.env`에만 보관하며 프론트엔드나 Git에 올리지 않습니다.

## 현재 구현 상태

| 단계 | 내용 | 상태 |
|---|---|---|
| 0 | 프로젝트 구조, FastAPI 진입점, 환경변수 샘플 | 완료 |
| 1 | F3001 공통 Tool 규격/레지스트리/오류 응답 기반 | 기반 구현 완료 (실제 API Tool 등록은 다음 단계) |
| 2 | API.SH Musinsa 검색·상세 Tool | 다음 작업 |
| 3 | Kakao Local 및 Open-Meteo 선택 Tool | 예정 |
| 4 | LangGraph 메인 Agent와 제약 판단/재계획 | 예정 |
| 5 | 이벤트 발행 및 로깅 Agent | 예정 |
| 6 | SQLite·계획 CRUD·로그 API | 예정 |
| 7 | 대화/계획/로그 프론트엔드 | 예정 |

제공된 `day01_fastapi` 원본 학습 코드는 `examples/day01_fastapi/`에 보존했습니다. 실제 앱은 새 `app/` 패키지에서 개발합니다.

## 개발 환경

- Python 3.10 이상
- FastAPI / Uvicorn
- SQLite (계획·로그 저장 단계에서 적용)
- HTML / CSS / JavaScript

## 실행 방법

```bash
# 1) 프로젝트 루트에서 가상환경 생성
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

# 2) 의존성 설치
pip install -r requirements.txt

# 3) 환경변수 파일 생성
# macOS / Linux
cp .env.example .env
# Windows PowerShell
# Copy-Item .env.example .env

# 4) 서버 실행
uvicorn app.main:app --reload
```

서버 실행 후 다음 경로를 확인합니다.

- 상태 확인: <http://localhost:8000/health>
- Tool 명세: <http://localhost:8000/api/tools>
- Swagger UI: <http://localhost:8000/docs>

## 테스트

```bash
python -m unittest discover -s tests -v
python -m compileall -q app tests
```

## GitLab + GitHub 동시 관리

저장소 remote 이름은 `gitlab`, `github`로 구분합니다. **이미 두 저장소 중 하나를 clone한 작업 폴더가 있다면 새로 `git init`하지 마세요.** 기존 `.git` 이력을 그대로 사용해야 합니다.

### A. 이미 clone한 저장소가 있는 경우 (권장)

1. ZIP 압축을 푼 뒤, 프로젝트 안의 파일과 폴더를 기존 clone 폴더의 루트로 복사합니다. 기존 `.git/` 폴더는 덮어쓰거나 삭제하지 않습니다.
2. 기존 remote를 확인하고 없는 remote만 추가합니다.

```bash
git remote -v
# 없는 경우에만 추가
git remote add gitlab https://lab.ssafy.com/1018ym/ai-core-pjt.git
git remote add github https://github.com/Yoomin-1234/ai-agent-planner.git
```

### B. 기존 clone이 없고 ZIP으로 새 작업 폴더를 시작하는 경우

```bash
git init -b main
git config user.name "본인 Git 이름"
git config user.email "본인 Git 이메일"
git remote add gitlab https://lab.ssafy.com/1018ym/ai-core-pjt.git
git remote add github https://github.com/Yoomin-1234/ai-agent-planner.git
```

원격 저장소가 이미 README 등의 커밋을 가지고 있는지 확인한 뒤 최초 이력을 통합합니다. 처음부터 무조건 force push하지 않습니다.

### 기능별 커밋 및 양쪽 push

각 기능을 구현하고 테스트를 통과시킨 뒤에는 기능별 커밋을 만들고 양쪽 remote로 push합니다.

```bash
# 변경사항 확인
git status

# 아래 스크립트가 변경사항을 커밋한 뒤 두 원격 저장소의 main으로 push
bash scripts/publish.sh "feat(tools): add Musinsa product search and detail tools"
```

스크립트를 사용하지 않을 때는 아래 명령을 직접 실행해도 됩니다.

```bash
git add app/tools/musinsa.py tests/test_musinsa_tools.py
git diff --cached --check
git commit -m "feat(tools): add Musinsa product search and detail tools"
git push gitlab HEAD:main
git push github HEAD:main
```

원격 저장소에 이미 별도 커밋(예: README)이 있으면 최초 push 전에 원격 이력을 먼저 확인하고 통합해야 합니다. 최초 push가 non-fast-forward로 거절되면 `git fetch gitlab github`로 이력을 확인한 뒤 각 원격 이력을 안전하게 통합하세요. 무조건 `--force`를 사용하지 않습니다. 인증·네트워크 연결이 필요한 push는 개발 PC의 Git 자격 증명으로 수행합니다.

## 보안 체크

- `.env`는 커밋하지 않습니다.
- `.env.example`에는 변수명만 두고 실제 키를 적지 않습니다.
- API 원문 오류·인증 헤더·키를 화면이나 실행 로그에 노출하지 않습니다.
- 상품 상세에서 확인되지 않은 소재·핏·방수·사이즈 재고를 추측하지 않습니다.
