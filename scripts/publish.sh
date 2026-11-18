#!/usr/bin/env bash
# 현재 변경사항을 커밋하고 GitLab/GitHub 양쪽 main으로 push한다.
# 사용법: bash scripts/publish.sh "feat(tools): add Musinsa search tool"
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo '사용법: bash scripts/publish.sh "커밋 메시지"' >&2
  exit 2
fi

for remote in gitlab github; do
  if ! git remote get-url "$remote" >/dev/null 2>&1; then
    echo "remote '$remote'가 없습니다. README의 Git 원격 저장소 설정부터 실행하세요." >&2
    exit 2
  fi
done

if [[ -n "$(git status --porcelain)" ]]; then
  git add -A
  git diff --cached --check
  git commit -m "$*"
else
  echo '새 변경사항은 없습니다. 기존 HEAD를 양쪽 remote로 push합니다.'
fi

# 현재 브랜치 HEAD를 각 원격의 main에 반영한다.
git push gitlab HEAD:main
git push github HEAD:main
