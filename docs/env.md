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

## 원본 문서 첨부

BE가 `documents`(S3 Presigned URL 목록)를 보내면 AI 서버가 원본 PDF/이미지를 내려받아 OpenAI Files API에 임시 업로드한 뒤 OCR 텍스트와 함께 분석한다. 
분석이 끝나면 업로드한 파일을 삭제한다.

- `OPENAI_DOCUMENT_DETAIL`: 원본 페이지를 읽는 해상도. `low` / `high` / `auto`. 기본값은 `high`
- `OPENAI_DOCUMENT_MAX_BYTES`: 한 가정통신문의 원본 문서 합계 최대 크기(byte). 기본값이자 최대값은 `52428800`(50MB)
- `OPENAI_DOCUMENT_DOWNLOAD_TIMEOUT_SECONDS`: S3 다운로드 timeout 초. 기본값은 `30`
- `OPENAI_DOCUMENT_FILE_TTL_SECONDS`: OpenAI에 올린 파일의 자동 만료 시간(삭제 실패 대비). `3600~2592000`, 기본값은 `3600`

`fileUrl`은 `https`의 S3 호스트(`s3.amazonaws.com`, 리전별 S3 호스트 및 그 버킷 서브도메인)만 허용하고, 리다이렉트는 따라가지 않는다.
다운로드나 업로드가 1회 재시도 후에도 실패하면 분석을 실패시키지 않고 원본 없이 기존 텍스트 분석으로 계속한다. 
이때 프롬프트와 날짜 검증도 기존 규칙(후보에서만 날짜 선택)을 그대로 적용한다. 
응답 `meta.requestedDocumentCount`와 `meta.attachedDocumentCount`로 원본 첨부 여부를 확인할 수 있고, 
원본에서만 읽은 날짜는 `meta.dateValidationWarnings`에 `DOCUMENT_ONLY_DATE`로 남는다.

## 기타

- `LOG_LEVEL`: 로그 레벨. 기본값은 `INFO`
