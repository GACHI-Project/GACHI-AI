# 가정통신문 분석 API 스펙

## 목적

BE가 가정통신문 저장에 필요한 `title`, `summary`, `items`를 AI 서버에서 한 번에 받을 수 있도록 최종 분석 API 계약을 정의한다.

AI 서버의 책임은 원문과 날짜 후보를 분석해 JSON을 반환하는 것이다. DB 저장 여부, 저장 모델 매핑, 사용자 확인 플로우는 BE가 담당한다.

## 엔드포인트

### `POST /ai/newsletters/analyze`

가정통신문 전체 분석 API다. 제목, 요약, 일정/마감/체크리스트 항목, 분석 메타데이터를 반환한다.

### `POST /ai/newsletters/extract-items`

기존 항목 추출 API다. `items` 응답 형식 검증과 비용 없는 rule-based baseline 확인 용도로 유지한다.

### `POST /ai/newsletters/prompt-preview`

LLM 호출 전 system/user prompt와 최종 분석 응답 JSON schema를 확인하는 API다. `responseSchema`는 `/ai/newsletters/analyze` 응답 구조를 기준으로 한다.

## Analyze 요청 스키마

`/ai/newsletters/analyze`는 기존 `extract-items` 입력 형식을 그대로 사용한다.

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `originalText` | `string` | 예 | 가정통신문 원문 |
| `translatedText` | `string \| null` | 아니오 | 번역 또는 OCR 보정 텍스트. 없으면 `null` |
| `language` | `string` | 아니오 | 원문 언어. 기본값은 `KO` |
| `referenceDate` | `date \| null` | 아니오 | 상대 날짜 해석 기준일. ISO-8601 날짜 |
| `timezone` | `string` | 아니오 | 날짜/시간 기준 타임존. 기본값은 `Asia/Seoul` |
| `dateCandidates` | `DateCandidate[]` | 아니오 | BE 또는 전처리 단계가 추출한 날짜 후보 목록 |

### `DateCandidate`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `candidateId` | `string \| null` | 아니오 | BE가 후보 추적에 사용할 수 있는 식별자 |
| `originalText` | `string` | 예 | 원문에 등장한 날짜 표현 |
| `normalizedDate` | `date` | 예 | 정규화된 날짜 |
| `startOffset` | `integer` | 예 | 원문 기준 시작 offset |
| `endOffset` | `integer` | 예 | 원문 기준 종료 offset |
| `extractionType` | `string \| null` | 아니오 | 후보 추출 방식. 예: `REGEX`, `OCR`, `MANUAL` |

```json
{
  "originalText": "2026학년도 체험학습 신청 안내\n5월 10일까지 참가 신청서를 제출해 주세요.",
  "translatedText": null,
  "language": "KO",
  "referenceDate": "2026-05-06",
  "timezone": "Asia/Seoul",
  "dateCandidates": [
    {
      "candidateId": "dc_1",
      "originalText": "5월 10일",
      "normalizedDate": "2026-05-10",
      "startOffset": 18,
      "endOffset": 24,
      "extractionType": "REGEX"
    }
  ]
}
```

## Analyze 응답 스키마

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `title` | `string` | 예 | 문서 제목. BE의 가정통신문 제목 저장값으로 사용 가능 |
| `summary` | `string` | 예 | 문서 요약. BE의 요약 저장값으로 사용 가능 |
| `items` | `ExtractedItem[]` | 예 | 일정, 마감, 체크리스트, 알림 항목 |
| `meta` | `object` | 예 | 분석 모드, 후보 개수 등 저장 비대상 메타데이터 |

### `ExtractedItem`

기존 `extract-items` 응답 형식을 유지한다.

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `type` | `schedule \| deadline \| checklist \| reminder` | 예 | 항목 분류 |
| `title` | `string` | 예 | 항목 제목. 문서 제목인 top-level `title`과 다름 |
| `selectedDateCandidate` | `SelectedDateCandidate \| null` | 예 | 선택된 날짜 후보. 날짜가 없으면 `null` |
| `dateStatus` | `confirmed \| ambiguous \| missing` | 예 | 날짜 신뢰 상태 |
| `datetime` | `string \| null` | 예 | 저장 가능한 날짜/시간 문자열. 없으면 `null` |
| `timezone` | `string` | 예 | 항목 날짜/시간 기준 타임존 |
| `evidenceText` | `string` | 예 | 원문 근거 |
| `confidence` | `number` | 예 | 0~1 범위 신뢰도 |
| `needsUserConfirmation` | `boolean` | 예 | 사용자 확인 필요 여부 |
| `confirmationQuestion` | `string \| null` | 예 | 사용자에게 물어볼 확인 질문 |

### `SelectedDateCandidate`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `index` | `integer` | 예 | 요청 `dateCandidates` 배열의 index |
| `candidateId` | `string \| null` | 예 | 요청 후보의 `candidateId` |
| `originalText` | `string` | 예 | 요청 후보의 `originalText` |
| `normalizedDate` | `date` | 예 | 요청 후보의 `normalizedDate` |

```json
{
  "title": "2026학년도 체험학습 신청 안내",
  "summary": "체험학습 참가 신청서를 5월 10일까지 제출해야 합니다.",
  "items": [
    {
      "type": "deadline",
      "title": "체험학습 참가 신청서 제출",
      "selectedDateCandidate": {
        "index": 0,
        "candidateId": "dc_1",
        "originalText": "5월 10일",
        "normalizedDate": "2026-05-10"
      },
      "dateStatus": "confirmed",
      "datetime": "2026-05-10",
      "timezone": "Asia/Seoul",
      "evidenceText": "5월 10일까지 참가 신청서를 제출해 주세요.",
      "confidence": 0.86,
      "needsUserConfirmation": false,
      "confirmationQuestion": null
    }
  ],
  "meta": {
    "mode": "rule_based_baseline",
    "dateCandidateCount": 1,
    "requiresLLMReview": true
  }
}
```

## 유지 여부 검토

- `dateCandidates` 입력 형식은 유지한다. 날짜 정규화 책임을 BE 또는 전처리 단계에 두고, AI 서버는 후보 중 하나를 선택한다.
- `items` 응답 형식은 유지한다. 기존 `extract-items` 소비 코드가 항목 구조를 그대로 검증할 수 있어야 한다.
- `items[].title`은 항목 제목이고, top-level `title`은 문서 제목이다. BE 매핑 시 두 필드를 구분해야 한다.
- `meta`는 저장 모델과 직접 매핑하지 않는다. 디버깅, 분석 모드 표시, 후보 개수 확인용이다.
- `selectedDateCandidate`, `evidenceText`, `confidence`, `needsUserConfirmation`, `confirmationQuestion`은 BE 저장 정책에 따라 저장하거나 무시할 수 있는 분석 보조 필드다.
- `datetime`은 `dateStatus`가 `confirmed`일 때만 캘린더/알림 저장 대상으로 보는 것을 권장한다. `ambiguous` 또는 `missing`은 사용자 확인 플로우로 넘긴다.

## 경계

- BE: 원문 저장, 날짜 후보 생성 또는 전달, 분석 결과 저장, 사용자 확인 처리.
- AI 서버: 원문 분석, 제목/요약/항목 추출, 날짜 후보 매칭, JSON 반환.
- AI 서버는 DB 테이블명, 저장 ID, ORM 모델을 요청이나 응답 스키마에 포함하지 않는다.
