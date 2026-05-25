# AI 서버 환경변수

## OpenAI 호출

- `OPENAI_ENABLED`: OpenAI 실제 호출 활성화 여부. 기본값은 `false`
- `OPENAI_API_KEY`: OpenAI API key. `OPENAI_ENABLED=true`일 때 필요
- `OPENAI_MODEL`: 사용할 모델. 기본값은 `gpt-4.1-mini`
- `OPENAI_BASE_URL`: OpenAI API base URL. 기본값은 `https://api.openai.com/v1`
- `OPENAI_TIMEOUT_SECONDS`: OpenAI 호출 timeout 초. 기본값은 `60`

비용 방지를 위해 로컬과 배포 기본값은 `OPENAI_ENABLED=false`로 둔다.
이 상태에서 `/ai/newsletters/analyze`는 기존 rule-based baseline으로 응답한다.

`OPENAI_ENABLED=true`인데 `OPENAI_API_KEY`가 없으면 `/ai/newsletters/analyze`는 `503`을 반환한다.
OpenAI 호출 또는 응답 파싱이 실패하면 `502`를 반환하고, 로그에는 상태 코드나 예외 사유를 남긴다.

## 기타

- `LOG_LEVEL`: 로그 레벨. 기본값은 `INFO`
