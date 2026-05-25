# 가정통신문 분석 구현 메모

이 문서는 API 명세서가 아니라 AI 서버 구현 경계와 유지 결정만 정리한다.
상세 request/response 명세는 노션을 기준으로 관리한다.

## 구현 범위

- AI 서버는 가정통신문 원문을 분석해 JSON 결과만 반환한다.
- DB 저장, 저장 모델 매핑, 사용자 확인 플로우는 BE가 담당한다.
- `POST /ai/newsletters/analyze`는 문서 제목, 요약, 항목, 메타데이터를 반환한다.
- `POST /ai/newsletters/extract-items`는 기존 항목 추출 baseline 확인용으로 유지한다.
- `POST /ai/newsletters/prompt-preview`는 LLM 호출 전 prompt와 응답 schema를 확인하는 용도로 유지한다.

## 유지 결정

- `dateCandidates` 입력 형식은 기존 `extract-items` 계약을 유지한다.
- `startOffset`, `endOffset`은 기존 계약과 동일하게 필수다.
- `items` 응답 형식은 기존 `extract-items` 응답 구조를 유지한다.
- top-level `title`은 문서 제목이고, `items[].title`은 항목 제목이다.
- `meta`는 저장 모델과 직접 매핑하지 않는 분석 보조 정보다.

## 책임 경계

- BE: 원문 저장, 날짜 후보 생성 또는 전달, 분석 결과 저장, 사용자 확인 처리.
- AI 서버: 제목/요약/항목 추출, 날짜 후보 매칭, JSON 반환.
- AI 서버 요청/응답에는 DB 테이블명, 저장 ID, ORM 모델을 포함하지 않는다.

## 문서 관리 원칙

- API 명세의 원본은 노션으로 둔다.
- repo 문서는 코드 변경 시 같이 봐야 하는 구현 결정만 남긴다.
- 한글 표 정렬이 깨지는 문제를 피하기 위해 긴 필드 표는 repo 문서에 두지 않는다.
