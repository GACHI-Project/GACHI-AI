# 가정통신문 분석 평가 스크립트

라벨링된 가정통신문 JSON을 기준 정답으로 사용해 `/ai/newsletters/analyze` 품질을 반복 측정한다.

## 목적

- rule-based baseline과 OpenAI adapter 결과를 같은 기준으로 비교한다.
- 프롬프트, 모델, 파서 수정 후 품질 회귀 여부를 확인한다.
- BE 저장 연동 전에 `title`, `summary`, `items` 응답 품질을 수치와 mismatch 리포트로 확인한다.

## 실행 방법

기본 실행은 비용이 발생하지 않는 baseline 모드다.

```powershell
python scripts/evaluate_newsletter_labels.py data/newsletter-labels
```

상세 리포트를 JSON으로 저장하려면 다음처럼 실행한다.

```powershell
python scripts/evaluate_newsletter_labels.py data/newsletter-labels --report-output reports/newsletter-eval-baseline.json
```

OpenAI 호출은 명시적으로 `--mode openai`를 줄 때만 실행한다.

```powershell
$env:OPENAI_API_KEY="..."
python scripts/evaluate_newsletter_labels.py data/newsletter-labels --mode openai --report-output reports/newsletter-eval-openai.json
```

CI나 로컬 기준선 확인에서 최소 F1을 강제하려면 `--fail-under-f1`을 사용할 수 있다.

```powershell
python scripts/evaluate_newsletter_labels.py data/newsletter-labels --fail-under-f1 0.75
```

## 라벨 JSON 형식

스크립트는 JSON 파일 하나, JSON 배열 파일, 또는 디렉터리 내 `*.json` 파일들을 입력으로 받는다.

현재 라벨링 데이터는 다음 형식을 사용한다.

```json
{
  "documentId": "doc_001",
  "documentTitle": "2026학년도 1학기 학습준비물 안내",
  "documentDate": "2026-03-24",
  "school": "서울세륜초등학교",
  "dateCandidates": [
    {
      "id": "dc_001_1",
      "raw": "2026. 5. 4.(월)",
      "resolved": "2026-05-04",
      "note": "행사 날짜"
    }
  ],
  "labels": [
    {
      "type": "checklist",
      "title": "준비물 준비",
      "evidenceText": "가정에서 직접 구매가 필요한 학습준비물",
      "selectedDateCandidateId": null,
      "dateStatus": "missing",
      "date": null,
      "target": "parent",
      "actionRequired": true,
      "schoolContext": null
    }
  ]
}
```

`originalText`가 없는 라벨은 `documentTitle`, `school`, `documentDate`, `labels[].evidenceText`를 이어 붙여 분석 입력으로 사용한다. 이 방식은 라벨셋 기반 회귀 확인용이며, OCR 결과 품질까지 포함해 평가하려면 JSON에 `originalText`를 추가해야 한다.

`input/expected`를 명시하는 확장 형식도 사용할 수 있다.

```json
{
  "sampleId": "newsletter-001",
  "input": {
    "originalText": "가정통신문 원문",
    "translatedText": null,
    "language": "KO",
    "referenceDate": "2026-05-24",
    "timezone": "Asia/Seoul",
    "dateCandidates": [
      {
        "candidateId": "dc_1",
        "originalText": "5월 25일",
        "normalizedDate": "2026-05-25",
        "startOffset": 10,
        "endOffset": 16,
        "extractionType": "REGEX"
      }
    ]
  },
  "expected": {
    "title": "가정통신문 제목",
    "summary": "가정통신문 요약",
    "items": [
      {
        "type": "deadline",
        "title": "동의서 제출",
        "evidenceText": "5월 25일까지 동의서를 제출해 주세요.",
        "selectedDateCandidateId": "dc_1",
        "dateStatus": "confirmed",
        "date": "2026-05-25"
      }
    ]
  }
}
```

## 평가 지표

- `item_precision`: 예측 항목 중 정답과 매칭된 비율
- `item_recall`: 정답 항목 중 예측과 매칭된 비율
- `item_f1`: precision과 recall의 조화 평균
- `title_accuracy`, `summary_accuracy`: 정규화된 문자열 완전 일치율
- `type_accuracy`: 매칭된 항목의 `type` 일치율
- `datetime_accuracy`: 매칭된 항목의 날짜 일치율
- `date_status_accuracy`: 매칭된 항목의 `dateStatus` 일치율

항목 매칭은 `type`, `dateStatus`, 날짜, 제목 유사도를 함께 사용한다. 제목 표현이 조금 달라도 같은 날짜와 분류가 맞으면 비교 대상으로 잡기 위한 기준이다.

## 데이터 관리

- 평가 데이터는 API 명세가 아니라 품질 검증용 정답셋이다.
- JSON 라벨 파일은 평가 재현을 위해 repo에 포함한다.
- PDF/JPG/PNG 원본은 Notion과 로컬 검수용으로 유지하고 repo에는 포함하지 않는다.
- 원본과 JSON은 `newsletter-001.json` ↔ `newsletter-001.pdf`처럼 같은 번호로 매칭한다.
- 라벨 기준은 `docs/newsletter-labeling-guide.md`를 따른다.
