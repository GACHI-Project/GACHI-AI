# #53 인수인계: 가정통신문 추출 개선

## 2026-09-24 이어받은 작업 요약 (원본 문서 첨부 + 재라벨링 기준 반영)

이 절은 인수인계 이후 추가한 작업이다. 아래 "이어서 작업할 팀원에게"부터는 기존 인계 내용이며,
평가 도구 사용법 중 달라진 부분은 이 절의 내용을 따른다.

- 브랜치: 기존 `bugfix/#53-newsletter-extraction`에서 이어서 작업한다. 새 PR은 만들지 않았다.
- 최신 코드 기준 AI 단위 테스트 98개 통과, ruff check/format 통과.
- 실제 모델 평가: gpt-4.1, 8조건, 원본 없이/원본 포함 각 1회씩 2차례 실행했다.
- 상세 기록
  - 원본 첨부 평가: [newsletter-document-attachment.md](newsletter-document-attachment.md)
  - 재라벨링 기준 프롬프트 반영(P1~P18): [newsletter-prompt-changes.md](newsletter-prompt-changes.md)

### 원본 문서 첨부 기능

OCR 오인식, 표/체크박스/강조 같은 배치 정보 손실을 보완하려고 원본 PDF/이미지를 OCR 텍스트와 함께 분석에 넘긴다.
OCR은 제거하지 않는다. 전체 문서 탭, 번역, 본문 중복 해시, 날짜 후보 offset에 계속 필요하다.

BE (GACHI-BE)
- `NewsletterPipelineService`: OCR에 실제로 사용한 파일을 페이지 순서대로 모은다. PDF는 원본, 이미지는 EXIF 보정 PNG.
- `AiNewsletterClient`: `documents[] {fileUrl, fileName, mimeType}`를 분석 요청에 추가한다.
  fileUrl은 S3 Presigned URL이며 만료 시간은 `AI_SERVER_PRESIGNED_MINUTES`(기본 5분, 1~10080분 검증).
- URL 생성 실패 시 documents를 빈 배열로 보내고 텍스트만으로 분석한다.
- 요청 로그: INFO는 길이/개수 요약만, DEBUG는 body 전체이되 URL은 가린다.

AI (GACHI-AI)
- `schemas.py`: `NewsletterAnalysisRequest.documents` 추가. 기본값 빈 배열이라 이전 BE 요청도 그대로 동작한다.
- `newsletter_document.py`(신규): Presigned URL 다운로드. https + `*.amazonaws.com`만 허용, 리다이렉트 차단, 크기 제한, 일시 오류 1회 재시도.
- `openai_adapter.py`: OpenAI Files API 업로드(purpose `user_data`, `expires_after`) → PDF는 `input_file`, 이미지는 `input_image`로 첨부(`detail` 기본 high) → 분석 후 `finally`에서 삭제.
  다운로드/업로드가 1회 재시도 후에도 실패하면 원본 없이 기존 텍스트 분석으로 계속한다.
  토큰 사용량을 로그로 남기고 응답 meta에 `requestedDocumentCount`, `attachedDocumentCount`를 기록한다.
- `newsletter_prompt.py`: 원본이 실제로 첨부된 경우에만 "원본 문서 사용 원칙"을 프롬프트 맨 끝에 넣는다.
  OCR과 원본이 다르면 원본 우선, "후보가 없으면 ambiguous" 계열 규칙은 원본에서도 날짜를 확인할 수 없을 때만 적용한다.
  원본이 없으면 이 원칙은 들어가지 않는다.
- `newsletter_validation.py`: 원본이 첨부되고 후보 없이 원본에서 읽은 confirmed 날짜는 강등하지 않고 `DOCUMENT_ONLY_DATE` 경고로 남긴다.
  후보를 골랐는데 틀린 경우의 기존 검증(`DATE_CANDIDATE_MISMATCH`, `SOURCE_DATE_CONFLICT`)은 그대로다.
- 환경변수: `OPENAI_DOCUMENT_DETAIL`, `OPENAI_DOCUMENT_MAX_BYTES`, `OPENAI_DOCUMENT_DOWNLOAD_TIMEOUT_SECONDS`, `OPENAI_DOCUMENT_FILE_TTL_SECONDS` ([env.md](env.md))
- 배포 순서: AI 서버를 먼저 배포해도 안전하다. documents가 없는 요청은 기존과 같이 동작한다.

### 프롬프트 변경

- 두 모드 공통: confirmed와 확인 요청(confirmationQuestion)을 함께 쓰지 않는다. 후보 연도가 문서 연도와 다르면 그 후보로 확정하지 않는다.
- 재라벨링(001~020)에서 확정한 판단 기준 P1~P18 반영. 상세와 관찰 포인트는 [newsletter-prompt-changes.md](newsletter-prompt-changes.md).

### 평가 도구 변경 (로컬 newsletter-prompt-check, 레포 밖)

- `compare.py`의 REPO는 수정하지 않아도 된다. `GACHI_AI_REPO` 환경변수를 쓰며, 없으면 명령을 실행한 폴더를 레포로 본다.
  아래 기존 안내의 "REPO를 자신의 레포 경로로 수정" 대신 환경변수를 설정한다.
- `run_suite.py`에 옵션 추가
  - `--with-documents`: `originals/<폴더>/`의 원본을 서버와 같은 방식으로 첨부해 분석한다. 결과 폴더는 `suite-results-docs-…`.
  - `--delay-seconds N`: 유료 호출 사이 대기. 원본을 high로 첨부하면 호출당 1만 토큰 이상이라 대기 없이 연속 호출 시 429가 발생했다. 40초에서 8조건 모두 성공.
- 원본 폴더: `originals/{wellbeing,fieldtrip,survey,album,supplies,family}/1.pdf`(album은 `1.png`).
  album-year-conflict는 album, family 두 케이스는 family 원본을 공유한다.
- `test_suite.py`의 한 테스트는 과거 결과 폴더를 직접 읽어서 폴더를 옮기면 실패한다. run_suite 동작과는 무관하다.

```powershell
cd <newsletter-prompt-check 경로>
$secureKey = Read-Host "OpenAI API 키" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
$env:OPENAI_MODEL = "gpt-4.1"
$env:GACHI_AI_REPO = "<GACHI-AI 레포 경로>"
$py = "<GACHI-AI 레포 경로>\.venv\Scripts\python.exe"

& $py -X utf8 .\run_suite.py --live --repeat 1 --delay-seconds 40
& $py -X utf8 .\run_suite.py --live --repeat 1 --with-documents --delay-seconds 40
```

### 평가 결과 요약 (gpt-4.1, 각 1회)

| 프롬프트 | 원본 없이 | 원본 포함 | 핵심 변화 |
| --- | --- | --- | --- |
| fe61a432 (원본 첨부 최초) | 5/8 | 6/8 | album의 금액/CMS 보존. 원본에서만 읽은 날짜 0건. album-year-conflict는 두 모드 모두 2026년 확정 |
| f6c258d7 (원본 규칙 수정 + P1~P18) | 5/8 | 5/8 (수동 판정 7/8) | 원본 포함에서 album-year-conflict를 2025년으로, family-missing-end 마감 9/18 15:00을 원본 기준으로 확정 |

- family-missing-end, album-year-conflict는 텍스트 전용 기준으로 채점되어 원본 포함 모드의 올바른 확정이 자동 채점에서는 실패로 나온다.
- 원본 없이는 album-year-conflict 납부를 여전히 2026-12-30으로 확정한다. 원문은 '30일(화)'이고 2026-12-30은 수요일이다.
- 원본 첨부 시 입력 토큰은 약 40% 늘어난다.

### 다음 작업 우선순위

#### 2026-09-28 추가 확인 및 오프라인 보완

- `OPENAI_DOCUMENT_DETAIL`의 코드 기본값은 이미 `high`다. 로컬 평가 시 `low`로 설정한
  PowerShell 환경변수와 배포 환경변수는 별도로 `high`인지 확인한다.
- 동일 프롬프트로 원본 첨부 `low`를 5조건 각 1회 확인했다. 세부 3조건에서
  fieldtrip은 날짜와 준비물을 추출했지만 스쿨뱅킹을 직접 이체처럼 표현했고,
  album-year-conflict는 원본의 2025년을 확정하지 못하고 둘 다 ambiguous가 됐으며,
  family-missing-end는 원본의 9/18 15:00을 올바르게 확정했다.
  `high`의 같은 조건 1회 결과와 비교하면 `low`를 동등하다고 판단할 근거가 부족하다.
  반복 평가를 하지 않았으므로 해상도 차이를 유일한 원인으로 단정하지 않는다.
- 날짜 후보의 바로 뒤 요일이 정규화 날짜와 다르면 `SOURCE_WEEKDAY_CONFLICT`로
  해당 항목만 ambiguous 처리하도록 보수적 검증을 추가했다. 예: 원문 `30일(화)`와
  후보 `2026-12-30`(수요일). 원본 PDF에서 후보 없이 읽은 날짜를 검증하는 기능은 아니다.
- 로컬 평가 도구에서는 원본 첨부 모드의 album-year-conflict와 family-missing-end에
  별도 정답 기준을 적용한다. CMS 자동 인출은 별도 송금 체크리스트 대신 해당 납부 항목의
  금액과 CMS 근거를 검사한다. fieldtrip의 안전 안내문 읽기는 체험 일정의 행동 또는
  별도 날짜 없는 reminder 모두 허용하되, 날짜가 있는 사건 3개는 유지해야 한다.
  이전 결과 파일 자체는 변경하지 않았으며 새 기준과
  기존 기준의 점수를 섞어 비교하지 않는다.
- 남은 검증: 실제 BE 업로드부터 AI 원본 첨부까지의 통합 흐름, 모델 반복 안정성,
  스쿨뱅킹 행동 주체와 번역 경계값의 수동 검토. BE의 `AiNewsletterClientTest`와
  `NewsletterAiAnalyzerTest`는 오프라인으로 통과했지만 실제 서버 간 통합 검증은 아니다.
  유료 모델 호출은 추가하지 않았다.

1. 완료: 날짜 후보 바로 뒤 요일이 정규화 날짜와 불일치하면 해당 항목을 ambiguous로 강등
2. 원본 첨부 시 후보가 원본과 같으면 후보를 선택하도록 프롬프트 보강 검토 (family-complete에서 후보 대신 원본 경로 사용)
3. 일부 완료: fieldtrip 안전 안내문 읽기의 두 유효한 표현을 평가 기준에 반영. P3 영향은 반복 모델 평가 후 판단
4. 완료: 로컬 평가 도구의 family-missing-end, album-year-conflict에 원본 포함 모드용 채점 기준 추가
5. P1~P18은 001~020 라벨 기준 평가로 따로 효과 확인
6. 주요 케이스 `--repeat 2~3` 반복 확인, 실제 BE 업로드 흐름(Presigned URL → AI 다운로드) 통합 확인

## 이어서 작업할 팀원에게

- 기존 PR #54, `bugfix/#53-newsletter-extraction` 브랜치에서 이어서 작업한다.
- 최신 코드는 단위 테스트 73개를 통과했지만 최종 프롬프트는 실제 모델 재검증 전이다.
- gpt-4.1로 검증한 직전 프롬프트의 SHA256은
  `05383722d66e3d01a49266fceffe299b52c15958093e1fbdbee64d549513e45f`이다.
  이 버전의 3/8 자동 통과를 최종 코드의 성적으로 인용하지 않는다.
- 사용자 요청으로 추가 유료 평가를 중단하고 인계한다. 새 PR 생성, 병합, 배포는 하지 않는다.
- 우선 순위: 평가 기준의 자동 인출 처리 정리 → 아래 6조건 재검증 → 전체 8조건 회귀 검사.
  실제 모델은 gpt-4.1을 명시한다. 저장소 기본값 mini와 혼동하지 않는다.

### 전달받을 로컬 자료

작업자 로컬 `newsletter-prompt-check` 폴더에서 다음 자료를 전달받는다.
API 키, 환경 파일과 인증 정보는 공유하거나 커밋하지 않는다.

- `run_suite.py`, `compare.py`, `suite_rubric.py`, `suite-cases.json`
- `suite-results-20260922-204709-766108` (가족발명교실 마감 후보 있음)
- `suite-results-20260922-205014-018418` (나머지 7조건)
- 원본 문서와 수동 전사/날짜 후보의 작성 근거

`compare.py`의 REPO는 작업자 절대경로이므로 자신의 레포 경로로 수정해야 한다.
과거 before/after 비교용 compare.py를 직접 실행하지 말고 run_suite.py를 실행한다.
run_suite.py는 compare.py의 공통 함수만 사용하며 현재 단일 호출 파이프라인을 실행한다.

```powershell
# API 키는 별도로 안전하게 설정한다. 아래 명령은 유료 호출 6~12회이다.
$env:OPENAI_MODEL = "gpt-4.1"
python -X utf8 "전달받은경로/run_suite.py" --live --repeat 1 --case fieldtrip --case survey --case album --case album-year-conflict --case family-missing-end --case family-complete
```

형식 통과와 의미 통과를 구분한다. 특히 연도 충돌, 마감 누락, 자동이체 행동 주체,
안전 안내문 읽기, 설문 행동 귀속, 이하/미만과 번역의 경계값을 수동 확인한다.
졸업앨범은 자동 인출 안내만 있을 때 체크리스트가 비어도 되지만 해당 납부 항목에서
금액과 CMS 방식은 확인할 수 있어야 한다. 기존 rubric은 납부 행동을 강제하므로 먼저 정합성을 맞춘다.
평가 기준을 수정하면 버전과 변경 사유를 남기고 기존 결과도 같은 기준으로 다시 채점한다.

## 현재 PR 범위

- 기존 1단계 OpenAI 분석을 유지한다. 형식 오류 재시도는 기존처럼 최대 2회이다.
- 발행일 제외, 사건별 제목, 날짜 없는 행동, 행동/설명 조건/일반 권고 구분 지침을 보완했다.
- 후보 index/ID/원문/정규화 날짜와 datetime이 불일치하면 해당 항목만 ambiguous로 바꾼다.
- ambiguous/missing의 선택 후보와 datetime을 비우고, 체크리스트와 요약은 보존한다.
- requiresLLMReview가 이미 true이면 날짜가 정상이거나 items가 비어 있어도 유지한다.
  날짜가 ambiguous인 항목이 있으면 기존 플래그와 관계없이 true로 설정한다.
- API 응답 필드, 모델, baseline, BE/FE 코드는 유지한다.
- 분석 요청은 strict Structured Outputs를 사용한다. 모델 출력 meta의 5개 키를 필수로 고정하고
  추가 키를 금지한다. 서버 후처리의 dateValidationWarnings는 기존처럼 응답 meta에 추가한다.
- 원문에 명시된 연월일과 후보가 충돌하거나 기간 시작일을 deadline으로 선택하면 ambiguous로 바꾼다.
  연도 상속은 명확한 같은 기간 표현에 한정하며 문서 제목의 학년도를 일괄 적용하지 않는다.
- 시각이 있는 일정의 datetime, 복수 사건 누락, 자동이체, 일반 영상 안내와 실행 요구 구분을 보완했다.
- 개선 실패가 확인된 2단계 전체 재검토는 제거했다. 추가 LLM 호출은 없다.

## 완료 범위와 한계

이 PR은 팀원이 이어서 개선하기 위한 중간 인계이며 #53 완료가 아니다.
단위 테스트 통과는 모델 품질 검증을 의미하지 않는다.
후처리는 후보 일치와 제한적인 원문 날짜 충돌을 검사한다. 발행일의 의미, 모든 연도 오류,
사건/행동 누락을 완전히 해결하지는 못한다. 원문에 없는 사건이나 행동을 코드로 만들어 넣지 않는다.
프롬프트의 금지 규칙도 모델이 무시할 수 있다. 아래는 과거 실패 이력이다.
최신 1회 평가에서 일부 개선됐지만 반복 안정성이 검증된 완료 목록은 아니다.

| 문제 | 확인한 증상 |
| --- | --- |
| 일반 안내의 과잉 추출 | 생명존중 안내의 상담/대화/영상 자료를 할 일로 생성 |
| 복수 사건 누락 | 현장체험학습의 행사/이체/준비물 누락 |
| 기간 종료일 선택 | 졸업앨범에서 신청/납부 시작일을 마감으로 선택 |
| 연도 충돌 | 2025년 문서의 잘못된 2026년 후보를 확정 |
| 설명 조건의 행동화 | 간주 동의를 별도 동의 행동으로 생성 |
| 조건 누락 | 가정당 1팀/최대 4명, 학년/학급별 상이 조건 누락 |

## 실험 이력

2026-09-22, gpt-4.1-mini, 문서별 각 1회 실행:
- 1단계 8조건 평가: 당시 부분 자동 검사 4/8. 수동 검토에서는 추가 오류가 발견됨.
- 2단계 실험: 강화된 검사 0/8. 이전 4/8과 검사 기준이 달라 직접 비교 불가.
- 2단계에서 학교폭력 조사 초안의 올바른 마감 5/8을 예시 화면의 5/13으로 변경함.
- 졸업앨범 검토는 items 원소가 객체가 아니어서 재시도까지 형식 검증 실패.
- 비용과 실패 지점을 늘린 2단계 검토는 이 PR에서 제외함.

평가 입력은 PDF 텍스트 추출/이미지 수동 전사와 수동 날짜 후보이다.
실제 OCR/BE 통합 테스트가 아니며, 반복 안정성도 아직 확인하지 않았다.

## 팀원 작업 순서

1. newsletter-regression-cases.md의 기대 결과를 기준으로 원문 기반 정답을 확정한다.
2. 누락과 잘못 추가된 행동을 각각 평가하고 모델 설정/추출 구조를 비교한다.
3. 한국어 사실 추출과 번역 분리 등은 별도 실험에서 효과 확인 후 채택한다.
4. data/newsletter-labels의 기존 top-level checklist와 설명성 reminder를 재라벨링한다.
5. BE/FE 계약을 확인한 후 운영 배포 여부를 결정한다.

## 배포 전 연동 조건

- missing: 날짜 입력을 강제하지 않고 문서 상세에서 체크리스트 표시.
- ambiguous: 사용자 날짜 확인, items=[]: 정상적인 일정 없음으로 처리.
- 체크리스트 노출을 캘린더 등록 여부와 분리.
- BE의 연도 없는 후보 추출/정규화, 시간과 allDay 및 기간 처리는 별도 수정.
- main 병합이나 운영 배포는 이번 작업에 포함하지 않는다.

## 로컬 검증

프로젝트 가상환경에서 pytest -q, ruff check app tests, ruff format --check app tests,
python -m compileall app을 실행한다. 실제 모델 평가는 API 비용이 발생하므로 별도 실행한다.

상세 원본/결과/기존 API 실행 도구는 작업자 로컬 newsletter-prompt-check 폴더에 보관하며
이 PR에는 포함하지 않는다. 팀원은 원본 문서와 평가 자료를 작업자에게 전달받아야 한다.
저장 응답 재검사 도구는 scripts/replay_newsletter_results.py로 레포에 포함했다.

## 추가 보완과 비용 없는 재검사

저장된 8조건 평가 폴더를 다음 명령으로 재검사할 수 있다.

```powershell
.\.venv\Scripts\python.exe scripts/replay_newsletter_results.py "결과폴더의 절대경로" --phase draft
```

- 각 `*-input.json`의 request/expected와 `*-run-*-draft-raw.json`을 읽는다.
- `--phase review` 또는 `--phase final`로 과거 검토/최종 응답도 선택할 수 있다.
- API 호출 없이 기존 응답의 후처리 전후 검사, 실패 항목, 수동 검토 기준을 출력한다.
- 응답 누락과 스키마 오류도 실패에 포함한다. 실패가 있거나 입력이 없으면 종료 코드 1이다.
- 이 결과는 새 프롬프트의 모델 재평가가 아니다. 누락된 항목을 복원하지 않으므로 과거 실패가 남을 수 있다.
- 기존 모델로 8조건을 재실행한 뒤에야 프롬프트의 내용 개선 여부를 판단할 수 있다.

strict schema는 형식 제약이며 의미 정확도를 보장하지 않는다.
설계 근거: [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
새 분석 스키마의 실제 API 수용은 아래 gpt-4.1 8조건 실행에서 확인했다.

### gpt-4.1 실제 재검증 (20:47 / 20:50)

`suite-results-20260922-204709-766108`과 `suite-results-20260922-205014-018418`:

- 모델은 gpt-4.1이며 기존 mini 실험과 프롬프트 개선 효과를 직접 비교할 수 없다.
- 8조건 모두 1회 응답, 형식 재시도 없음. strict schema의 실제 API 수용을 확인했다.
- 당시 자동 검사 3/8 통과(생명존중, 준비물, 가족발명교실 마감 후보 있음).
- 가족발명교실 통과 응답에도 '3팀 이하'를 '3팀 미만'으로 바꾼 의미 오류가 있었다.
- 현장체험학습은 안전 안내문 읽기 누락, 잔액 확인 대신 '이체하기' 생성이 남았다.
  790원은 content/summary에 있으므로 detail 검사 실패를 금액 전체 누락으로 해석하면 안 된다.
- 학교폭력 조사는 시작 schedule과 마감 deadline으로 분리하고 행동을 시작 항목에 붙였다.
- 졸업앨범 날짜는 정상이나 연도 충돌 조건에서 납부만 2026년으로 잘못 확정했다.
  자동 인출의 빈 체크리스트 자체는 허용되며 납부 행동을 강제하는 기존 rubric과 불일치한다.
- 가족발명교실 마감 후보 누락 시 시작일을 마감으로 확정했다. 연속 괄호를 놓친
  날짜 검증 패턴을 수정하고 재현 테스트를 추가했다.
- 이 결과 이후 경계값 보존, 자동이체 행동 주체, 읽기 요구, 설문 기간, 항목별 연도 지침을
  추가 보완했다. 보완한 프롬프트의 새 모델 실행은 아직 하지 않았다. 추가 비용 승인 후 재검증한다.
- 새 프롬프트 지침 구성 참고: [OpenAI GPT-4.1 guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-4.1).

### 2026-09-22 초기 오프라인 검증 결과 (실제 모델 재검증 이전)

- 단위 테스트 69개 통과. 전체 ruff check/format, app/scripts 컴파일, git diff --check 통과.
- suite-results-20260922-100655-161819의 draft 8개를 API 호출 없이 재검사했다.
- 졸업앨범에서 시작일을 마감으로 선택한 응답은 DEADLINE_RANGE_START로 ambiguous 처리됐다.
- 전체 의미 검사 통과는 여전히 0/8이다. 기존 응답의 누락/과잉 행동/조건 누락을 코드가
  복원하거나 제거하지 않으므로 이 수치를 새 프롬프트의 평가 결과로 사용하면 안 된다.
- 원문 연도/월/일 충돌, 기간 내 연도 상속, 다음 해 명시 일정 보존, UTF-16 위치 처리,
  스키마 오류/응답 누락의 평가 실패 처리는 합성 회귀 테스트로 확인했다.
