# 가정통신문 항목 추출 설계

## 목적

가정통신문 본문에서 일정, 마감, 체크리스트, 알림 항목을 추출합니다.

핵심 원칙은 날짜를 AI가 새로 만들지 않게 하는 것입니다. 구체적인 날짜는 백엔드나 전처리 단계에서 만든 `dateCandidates` 중 하나만 선택해야 합니다.

## 엔드포인트

### `POST /ai/newsletters/extract-items`

비용 없이 실행되는 rule-based baseline입니다. OpenAI API를 붙이기 전에도 스키마, 날짜 후보 매칭, 샘플 케이스를 확인할 수 있습니다.

### `POST /ai/newsletters/prompt-preview`

LLM에 전달할 system/user prompt와 응답 JSON schema를 생성합니다. ChatGPT Plus에서 수동 실험하거나, 추후 OpenAI API 호출에 그대로 사용할 수 있습니다.

## 요청 예시

```json
{
  "originalText": "5월 10일까지 참가 신청서를 제출해주세요.",
  "translatedText": null,
  "language": "KO",
  "referenceDate": "2026-05-06",
  "timezone": "Asia/Seoul",
  "dateCandidates": [
    {
      "candidateId": "dc_1",
      "originalText": "5월 10일",
      "normalizedDate": "2026-05-10",
      "startOffset": 0,
      "endOffset": 6,
      "extractionType": "REGEX"
    }
  ]
}
```

## 추출 규칙

- `confirmed`는 항목이 제공된 date candidate 중 하나를 사용할 때만 부여합니다.
- 날짜 표현이 있지만 후보 매칭이 불확실하면 `ambiguous`로 둡니다.
- 실행 가능한 체크리스트인데 날짜가 없으면 `missing`으로 둡니다.
- `evidenceText`는 원문 근거를 짧게 담습니다.
- 캘린더와 알림 생성은 `confirmed` 항목만 대상으로 삼습니다.

## 작업 흐름

1. 백엔드 또는 전처리 단계에서 날짜 후보를 만듭니다.
2. AI 서버에 원문과 `dateCandidates`를 전달합니다.
3. `extract-items`로 비용 없는 baseline 결과를 먼저 확인합니다.
4. 부족한 케이스는 `prompt-preview` 결과를 ChatGPT Plus에 넣어 비교합니다.
5. 충분히 안정화된 뒤 OpenAI API 호출을 AI 서버 내부에 붙입니다.
