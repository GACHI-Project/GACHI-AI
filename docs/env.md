# AI 서버 환경변수

## 필수

- `OPENAI_API_KEY`: 추후 LLM API 호출을 붙일 때 사용할 OpenAI API key

## 선택

- `LOG_LEVEL`: 로그 레벨. 기본값은 `INFO`

## 현재 상태

현재 구현은 OpenAI API를 직접 호출하지 않습니다. `OPENAI_API_KEY`는 기존 EC2 compose 환경과 향후 LLM client 연결을 고려해 유지합니다.
