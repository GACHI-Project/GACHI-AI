# GACHI-AI

GACHI 프로젝트의 AI 서버입니다. BE와 분리된 FastAPI 애플리케이션으로 운영하며, 기존 EC2 `docker-compose`의 `ai` 서비스로 배포합니다.

## 역할

- 가정통신문 원문과 날짜 후보를 기반으로 제목, 요약, 일정/마감/체크리스트 항목을 분석합니다.
- AI 서버는 분석 결과 JSON만 반환하고, DB 저장은 BE가 담당합니다.
- `OPENAI_ENABLED=true`일 때 OpenAI API를 호출하고, 기본값에서는 비용 없는 rule-based baseline으로 응답합니다.
- 기존 baseline API와 prompt-preview API를 유지합니다.

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
- `POST /ai/newsletters/analyze`: 제목, 요약, 항목을 함께 반환하는 가정통신문 전체 분석
- `POST /ai/newsletters/extract-items`: 날짜 후보 기반 baseline 항목 추출
- `POST /ai/newsletters/prompt-preview`: LLM 입력용 prompt와 최종 분석 response schema 미리보기

## 분석 평가

라벨링된 가정통신문 JSON으로 baseline 또는 OpenAI adapter 결과를 평가할 수 있습니다.

```powershell
python scripts/evaluate_newsletter_labels.py data/newsletter-labels --report-output reports/newsletter-eval-baseline.json
```

기본 모드는 비용이 발생하지 않는 baseline입니다. 실제 OpenAI 호출은 `--mode openai`를 명시한 경우에만 실행합니다.

## 작업 규칙

- 기본 브랜치: `develop`
- 브랜치 예시: `feat/#1-feature-name`, `chore/#1-ci-cd-setup`
- 커밋 타입: `feat`, `fix`, `refactor`, `docs`, `style`, `chore`
- `main`, `develop` 직접 커밋은 지양하고 PR로 병합합니다.

## 문서

- `docs/env.md`: 환경변수
- `docs/deploy.md`: Docker image와 EC2 배포 방식
- `docs/newsletter-extraction.md`: 가정통신문 분석 구현 경계와 유지 결정
- `docs/newsletter-labeling-guide.md`: 정답 데이터 라벨링 기준
- `docs/newsletter-evaluation.md`: 라벨링 데이터 기반 분석 평가 실행 방법
