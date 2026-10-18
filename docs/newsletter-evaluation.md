# 실제 OCR 입력 기반 가정통신문 평가

## 설치와 안전 경계

```powershell
python -m pip install -r requirements.txt
```

Windows에서는 tzdata가 IANA 시간대 비교에 필요하다. 기본 baseline 모드와 데이터 준비,
입력 검증은 유료 API를 호출하지 않는다. 실제 OpenAI 호출은 `--mode openai`에서만 실행한다.
평가 명령은 OPENAI_ENABLED 환경 변수를 실행 중에만 제어하고 종료 시 이전 값으로 복원한다.
서버 API나 운영 프롬프트의 동작은 변경하지 않는다.

## 1. 기존 라벨 이전

```powershell
python -X utf8 scripts/prepare_newsletter_dataset.py 기존라벨.json --output local-newsletter-eval/draft.json
```

배열, samples 배열 또는 개별 JSON을 읽는다. 이미 이전한 pilot 10건은
`data/newsletter-pilot/pilot-labels-v3.json`에 있다. 원본 대조 내역과 검수 방법은
`newsletter-pilot-migration.md`에 기록했다. OCR 입력은 별도 연결 전까지 null로 유지한다.
2차 pilot 10건(pilot_011~020)은 처음부터 v3 스키마로 작성한
`data/newsletter-pilot/pilot-labels-new.json`에 있으며 이전 단계 없이 2번의 BE 결과 연결부터 진행한다.
기존 `data/newsletter-labels`의 입력 없는 라벨은 더 이상
근거문을 합성해서 평가하지 않는다. 이 파일들도 같은 도구로 이전하고 실제 OCR을 연결해야 한다.
준비 도구는 기존 출력 파일이나 원본 라벨을 덮어쓰지 않는다.

## 2. BE 추출 결과 연결

BE 일괄 추출 manifest의 sampleId를 라벨의 sampleId와 같게 지정한다.
BE 결과 폴더에는 `<sampleId>.json`이 있어야 한다.

```powershell
python -X utf8 scripts/prepare_newsletter_dataset.py data/newsletter-pilot/pilot-labels-v3.json --ocr-results ../GACHI-BE/local-newsletter-ocr/results --output local-newsletter-eval/pilot-ready.json
```

SUCCESS 결과만 허용한다. PARTIAL/FAILED, 다른 ID, 잘못된 후보 위치는 오류다.
BE의 UTF-16 후보 위치를 Python 문자열 위치로 변환한 뒤 원문 일치를 검증한다.
후보를 본문에서 재검색하거나 0번 위치로 대체하지 않는다.
실제 originalText, dateCandidates, referenceDate와 sourceFiles를 연결한다.
원본 경로와 SHA-256은 페이지 순서대로 보관하며, 만료되는 S3 URL을 저장하거나 재사용하지 않는다.
데이터 연결만으로 draft를 reviewed로 변경하지 않는다.

## 3. 입력 검증과 비용 없는 평가

검수 완료 후 각 샘플의 `metadata.annotationStatus`를 reviewed로 변경한다.

```powershell
python -X utf8 scripts/evaluate_newsletter_labels.py local-newsletter-eval/pilot-ready.json --validate-only
python -X utf8 scripts/evaluate_newsletter_labels.py local-newsletter-eval/pilot-ready.json --report-output reports/pilot-baseline.json
```

초안으로 개발 경로만 확인할 때는 `--allow-drafts`를 명시한다. 실제 OCR이 없는 초안은
이 옵션이 있어도 실행하지 못한다. 입력 오류는 해당 sampleId와 안전한 오류 코드를 표시한다.
샘플 ID 중복, 후보 ID 중복, 원문/위치 불일치, 기준일 누락, 잘못된 정답 날짜 상태를 검증한다.
원격 documents URL은 평가 입력에서 금지한다. 원본은 로컬 sourceFiles로만 지정한다.

BE #213에서 실행한 가족발명교실 결과는 다음처럼 연결할 수 있다.

```powershell
python -X utf8 scripts/prepare_newsletter_dataset.py data/newsletter-pilot/family-invention-label.json --ocr-results ../GACHI-BE/local-newsletter-ocr/live-family-check --output local-newsletter-eval/family-ready.json
python -X utf8 scripts/evaluate_newsletter_labels.py local-newsletter-eval/family-ready.json --allow-drafts --report-output reports/family-baseline.json
```

이 사례는 본문에 마감일이 있지만 BE 후보에 9.18.이 없는 회귀 사례다.
baseline 성능이 낮아도 평가 도구 자체의 실패와 구분한다. 정답을 후보 누락에 맞춰 바꾸지 않는다.

## 4. 실제 모델 평가

API 키는 별도로 안전하게 설정한다. 기존에 사용하던 모델을 명시해 비교한다.

```powershell
$env:OPENAI_MODEL = "gpt-4.1"
$env:OPENAI_DOCUMENT_DETAIL = "high"
# 텍스트 전용
python -X utf8 scripts/evaluate_newsletter_labels.py local-newsletter-eval/pilot-ready.json --mode openai --delay-seconds 40 --report-output reports/pilot-text.json
# 원본 포함
python -X utf8 scripts/evaluate_newsletter_labels.py local-newsletter-eval/pilot-ready.json --mode openai --with-documents --delay-seconds 40 --report-output reports/pilot-documents.json
```

원본 포함은 로컬 파일을 LoadedDocument로 만들어 기존 adapter에 전달한다.
모든 파일의 존재, 지원 형식, 전체 크기, 기록된 SHA-256을 먼저 검사한다.
원본 검증만 하려면 `--mode openai --with-documents --validate-only`를 사용한다. 이때도 API 호출은 없다.
baseline은 이미지를 읽지 않으므로 `--with-documents`와 함께 사용할 수 없다.
모델 응답의 attachedDocumentCount가 요청 수와 다르면 텍스트 fallback을 정상 결과로 채점하지 않는다.
`--delay-seconds`는 실제 모델 샘플 사이의 대기 시간이다. 첫 호출 전이나 baseline에서는 대기하지 않는다.
진행 상황은 sampleId와 순서만 출력하며 원문이나 인증 정보를 출력하지 않는다.
호출/첨부 실패는 실패 샘플로 남기며 실행 종료 코드는 1이다. 비밀값이 포함될 수 있는 예외 원문은 저장하지 않는다.

## 정답 형식

```json
{
  "schemaVersion": "gachi-newsletter-evaluation-v3",
  "sampleId": "example_001",
  "offsetEncoding": "codepoint",
  "input": {
    "originalText": "9월 28일까지 신청서를 제출하세요.",
    "referenceDate": "2026-10-18",
    "timezone": "Asia/Seoul",
    "dateCandidates": [{
      "candidateId": "dc_1", "originalText": "9월 28일", "normalizedDate": "2026-09-28",
      "startOffset": 0, "endOffset": 6, "extractionType": "REGEX"
    }]
  },
  "metadata": {"annotationStatus": "reviewed", "labelVersion": "3"},
  "expected": {"items": [{
    "type": "deadline", "title": "신청서 제출", "dateStatus": "confirmed",
    "datetime": "2026-09-28", "endDatetime": null, "periodStartDatetime": null,
    "timezone": "Asia/Seoul", "needsUserConfirmation": false,
    "checklistItems": [{"content": "신청서 제출", "contentPatterns": ["신청서", "제출"]}]
  }]}
}
```

예시는 형식 설명용이며 실제 OCR을 대신하는 데이터가 아니다.

## 점수와 검수 범위

- 항목 precision/recall/F1: 제목 중심으로 사건을 연결한 뒤 누락과 추가를 기록한다.
- date_accuracy: 날짜 비교. time_accuracy: 시각 및 시각 유무 비교.
- datetime_accuracy: 날짜와 시각 정밀도를 함께 비교한다. 날짜만 있는 값과 임의 자정은 다르다.
  동일 시점의 UTC/KST 표현은 같게 비교한다.
- end_datetime_accuracy, period_start_datetime_accuracy: 추가 시간 필드 비교.
- type_accuracy, date_status_accuracy, needs_user_confirmation_accuracy: 계약 필드 비교.
- checklist precision/recall/F1: 명시된 표현 또는 패턴으로 행동을 일대일 대응시킨다.
  누락, 불필요한 추가, 중복 목록과 detail 조건 정확도를 별도로 출력한다.
- 정답 checklistItems가 누락된 항목은 미평가다. []는 할 일 없음의 정답이다.
- 날짜/분류/조건 정확도는 매칭된 항목 기준이다. 놓친 항목은 항목 recall 및 누락 목록으로 확인한다.
  전체 보고서의 metric_sample_counts로 각 점수의 평가 범위를 함께 확인한다.
- 호출 실패 샘플은 전체 샘플 수에 포함하고 항목 점수 0으로 기록한다. 다른 정확도는 미평가로 남긴다.
- 제목/요약 일치와 유사도는 진단 값이며 의미 적합성의 자동 판정이 아니다.
  동의어, 조건 적용 대상, 패턴의 적절성, 교차 항목 중복은 사람이 검수한다.
- confidence, 다국어 번역, conversationTopics, meta는 이번 채점에서 제외했다고 보고서에 표시한다.

리포트에는 코드 커밋/dirty 상태, 평가기/프롬프트 해시, 데이터 해시와 라벨 버전,
기준일, 모델, 문서 detail 설정, 실제 첨부 수와 문서 해시를 기록한다.
리포트는 원문 및 예측을 포함할 수 있으므로 Git에서 제외된 reports/에 비공개 보관한다.
`--fail-under-f1 0.75`로 항목 F1 기준을 강제할 수 있지만 시간/체크리스트 전체 통과를 뜻하지는 않는다.
기준을 지정하지 않은 실행의 종료 코드 0은 호출/입출력 경로가 성공했다는 뜻이지
모든 분석이 정답이라는 뜻이 아니다. 실제 pilot 실행 관찰과 자동 점수의 한계는
`newsletter-pilot-validation.md`를 참고한다.

## 테스트

```powershell
python -m pytest
ruff check .
ruff format --check .
```

실제 OCR 입력 가져오기, UTF-16 위치, 시간 정밀도, 기간/확인 상태, 체크리스트,
원본 누락과 첨부 fallback, 비밀값 비출력, 환경 복원을 외부 호출 없이 검증한다.
