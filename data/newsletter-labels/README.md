# 가정통신문 라벨링 데이터

이 디렉터리는 가정통신문 분석 평가에 사용하는 JSON 정답셋을 둔다.

## 파일 매칭

- JSON 파일명과 원본 파일명은 같은 번호를 사용한다.
- 예: `newsletter-001.json`의 원본은 `newsletter-001.pdf`
- 원본 파일 확장자는 `pdf`, `jpg`, `png`를 사용할 수 있다.
- `hwp`는 현재 파이프라인 입력으로 사용하지 않는다.

## 커밋 기준

- JSON 라벨 파일은 평가 재현을 위해 repo에 포함한다.
- PDF/JPG/PNG 원본은 로컬 검수와 Notion 공유용으로 유지하고 repo에는 포함하지 않는다.
- 원본이 필요하면 Notion 자료 또는 로컬 파일명 번호로 JSON과 매칭한다.

## 현재 JSON 스키마

현재 라벨 파일은 다음 구조를 사용한다.

```json
{
  "documentId": "doc_001",
  "documentTitle": "문서 제목",
  "documentDate": "2026-03-24",
  "school": "학교명",
  "dateCandidates": [
    {
      "id": "dc_001_1",
      "raw": "5월 20일",
      "resolved": "2026-05-20",
      "note": "제출 마감일"
    }
  ],
  "labels": [
    {
      "type": "schedule | deadline | checklist | reminder",
      "title": "항목 제목",
      "evidenceText": "원문 근거 텍스트",
      "selectedDateCandidateId": "dc_001_1 또는 null",
      "dateStatus": "confirmed | ambiguous | missing",
      "date": "YYYY-MM-DD 또는 null",
      "target": "parent | student | both",
      "actionRequired": true,
      "schoolContext": "학교 문화 맥락 설명 또는 null"
    }
  ]
}
```

`originalText`가 없는 라벨은 평가 스크립트가 `documentTitle`, `school`, `documentDate`, `labels[].evidenceText`를 이어 붙여 baseline 입력으로 사용한다.
OCR 원문까지 평가하려면 추후 JSON에 `originalText`를 추가한다.
