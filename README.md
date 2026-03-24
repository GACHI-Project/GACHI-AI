# GACHI-AI

GACHI 프로젝트 AI 서버(FastAPI) 레포지토리입니다.

## 문서
- `docs/env.md`: 환경 변수 가이드
- `docs/deploy.md`: 이미지 태그/배포 가이드

## 협업 규칙
- 기본 브랜치: `develop`
- 브랜치 전략: `feat/xx`, `refac/xx`, `hotfix/xx`, `chore/xx`, `design/xx`, `bugfix/xx`
- 커밋 타입: `feat`, `fix`, `refactor`, `docs`, `style`, `chore`
- `main`, `develop` 직접 push 금지, PR 승인 후 머지
- CI 체크(`build-and-push`) 통과 후 머지

## 배포 태그 규칙
- `develop` push: `<dockerhub-id>/gachi-ai:develop`
- `main` push: `<dockerhub-id>/gachi-ai:latest`
