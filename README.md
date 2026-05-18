# GACHI-AI

GACHI 프로젝트의 AI 서버입니다. 백엔드와 분리된 FastAPI 애플리케이션으로 운영하며, 기존 EC2 `docker-compose`의 `ai` 서비스로 배포합니다.

## 역할

- 가정통신문 원문과 날짜 후보를 기반으로 일정, 마감, 체크리스트, 알림 항목을 추출합니다.
- OpenAI API 호출 전에도 검증할 수 있도록 비용 없는 rule-based baseline을 제공합니다.
- 실제 LLM에 전달할 prompt-preview API를 제공합니다.

## 로컬 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Windows PowerShell에서는 다음처럼 가상환경을 활성화합니다.

```powershell
.\.venv\Scripts\Activate.ps1
```

## 주요 엔드포인트

- `GET /ai/health`: 헬스체크
- `GET /ai/docs`: Swagger UI
- `POST /ai/newsletters/extract-items`: 날짜 후보 기반 baseline 추출
- `POST /ai/newsletters/prompt-preview`: LLM 입력용 prompt와 response schema 미리보기

## 작업 규칙

- 기본 브랜치: `develop`
- 브랜치 예시: `feat/#1-feature-name`, `chore/#1-ci-cd-setup`
- 커밋 타입: `feat`, `fix`, `refactor`, `docs`, `style`, `chore`
- `main`, `develop` 직접 커밋은 피하고 PR로 병합합니다.

## 문서

- `docs/env.md`: 환경변수
- `docs/deploy.md`: Docker image와 EC2 배포 방식
- `docs/newsletter-extraction.md`: 가정통신문 추출 API와 프롬프트 흐름
- `docs/newsletter-labeling-guide.md`: 정답 데이터 라벨링 기준
