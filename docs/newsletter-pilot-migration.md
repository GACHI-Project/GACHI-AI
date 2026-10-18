# Pilot 라벨 v3 이전 내역

`data/newsletter-pilot/pilot-labels-v3.json`은 기존 로컬 `labeling_pilot/pilot_gold_labels.json`
10건을 저장소에서 이어서 검수할 수 있도록 이전한 데이터다.
`family-invention-label.json`은 BE #213에서 실제 OCR에 성공한 문서를 연결하기 위한 추가 회귀 초안이다.

## 반영한 변경

- 문서 정보와 `input`, `expected`를 분리하고 문서 식별자는 `sampleId`로 통일했다.
- 실제 OCR이 없는 `input`은 null로 유지했다. 정답 근거를 본문으로 합성하지 않는다.
- 수동 날짜 후보는 `legacyDateCandidates`로 옮겼다. 실제 입력 후보로 사용하지 않는다.
- 근거 없는 00:00과 23:59:59를 제거하고 명시된 시각은 보존했다.
- 겨울방학, 휴강, 캠프, 아카데미, 늘봄 운영 기간과 운동회 종료 시각을 기존 근거에 맞춰 추가했다.
- 설문 마감은 한 건으로 유지하고 접수 시작일을 `periodStartDatetime`으로 추가했다.
- 일반 감염병 대응 안내와 학교운영위원 임기 설명은 현재 실행 항목에서 제외했다.
- 모델 `confidence=1.0`을 사람 정답의 확신도로 사용하던 필드를 제거했다.

## 원본 대조 검수: v3.1

2026-10-18에 PDF 8건, HWP에서 내보낸 2페이지 PDF 1건, JPG 1건의 모든 페이지를
이미지로 대조했다. 모델 예측을 읽기 전에 정답을 수정했다. `reviewMethod`에
`assistant_visual_source_review`를 기록했으며, 사람 여러 명의 독립 라벨링이나 합의 검수를
수행했다는 뜻은 아니다. 논문에서 사람 정답셋으로 사용할 때는 담당자의 최종 승인이 필요하다.

- pilot_001: 누락된 돌봄교실 기간과 08:00~18:30을 추가했다. 방과후학교 행의 2024년 충돌은 ambiguous 유지.
- pilot_002: 머리말, 개인정보 보유기간, 서명란은 2023년 사건의 독립 근거다.
  하단 발행일 2022.3.2.와 구분하여 제출은 2023-03-07, documentDate는 null 유지.
- pilot_003: 두 학년 그룹의 09:00~12:10과 준비물을 대조했다. 안내 조건을 확인 과제로 만들지 않는다.
- pilot_004: 체육복/운동화 준비만 현재 과제로 남기고 추후 저체력 판정자 교실 참석은 제외했다.
- pilot_005: 지원 혜택 안내이며 지금 지원금 신청을 요구하지 않아 items=[]로 수정했다.
- pilot_006: 두 휴업일은 일정으로 보존하고 이미 끝난 돌봄 수요조사를 새 신청으로 만들지 않는다.
- pilot_007: 마감 한 건과 설문 시작, 대상 및 첫째 기준 1회 조건을 보존했다.
- pilot_008: 일반 안전 수칙은 제외하고 명시적인 자녀와 영상 시청 요청만 reminder로 남겼다.
- pilot_009: 선출 완료 시기를 특정일 투표 행사로 만들지 않는다. 세부 일정이 추후 안내이므로 items=[]다.
- pilot_010: 학년별 하교 시각은 행사 시작/종료 시각이 아니다. 세 날짜는 보존하되 임의의 확인 과제를 제거했다.

저장소의 라벨은 `annotationStatus=reviewed`, `labelVersion=3.1`이다. 원문 배포와 개인 로컬 경로
커밋을 피하기 위해 실제 OCR은 별도 로컬 데이터셋에 연결한다. 저장소 파일의 `input=null`과
`inputStatus=pending_actual_ocr`는 그 연결이 필요하다는 뜻이며 OCR을 성공한 것처럼 합성하지 않는다.
원본 파일 SHA-256과 변경 근거는 각 샘플 metadata에 기록했다.

추가 가족발명교실 라벨은 별도 초안이다. 이번 pilot 10건 검수 상태를 자동 적용하지 않는다.
초안 실행을 위한 `--allow-drafts`는 개발 확인용이며 확정 정답셋 평가로 보고하지 않는다.

BE 추출 시 기존 pilot ID를 manifest의 sampleId로 사용하면 수동 복사 없이 연결할 수 있다.
HWP 파일은 PDF로 변환한 뒤 같은 ID를 유지한다. 변환 전 이름은 sourceFile 등 메타데이터에 보관한다.
준비 및 평가 명령은 `newsletter-evaluation.md`를 참고한다.

## 2차 pilot 라벨: pilot_011~020

`data/newsletter-pilot/pilot-labels-new.json`은 1차 pilot과 원본이 겹치지 않는 신규 가정통신문 10건의 정답이다.
처음부터 v3 스키마(`schemaVersion=gachi-newsletter-evaluation-v3`)로 작성했으므로 이전 단계는 거치지 않았다.

### 작성 방식

- 원본 PDF 전체 페이지를 이미지로 대조해 AI 보조 초안(`annotationStatus=draft`)을 작성했다.
  초안은 `newsletter-labeling-guide.md` v3 기준과 1차 pilot 라벨의 표현 방식을 따랐다.
- 초안 작성 시 OCR 결과, 날짜 후보, 모델 예측을 보지 않았다. `input`은 null로 두고 실제 BE OCR 결과로만 연결한다.
- 담당자가 원본과 다시 대조해 수정한 뒤 `annotationStatus=reviewed`,
  `reviewMethod=assistant_draft_human_visual_review`로 변경했다. 1인 검수이며 여러 명의 합의 검수는 아니다.
- `sourceFile`은 BE manifest 입력 파일명(`pilot_0NN.pdf`)이고 원본 제목은 `documentTitle`에 보관한다.
  원본 SHA-256은 각 샘플 `metadata.sourceOriginalSha256`에 기록했다.
- 1차 `pilot-labels-v3.json`과 파일을 분리했다. 1차 보고서에 기록된 데이터 해시를 보존하고,
  두 세트의 BE OCR 결과 폴더가 다르기 때문이다.

### 검수 결정

- pilot_011: 학교 지원 물품은 제외하고 '가정에서 직접 구매' 개인물품만 날짜 없는 reminder로 보존한다.
  '학년별, 학급별로 상이할 수 있음'은 detail에 둔다.
- pilot_012: 신청 기간과 접수 시작 시각이 없어 선착순 신청은 reminder다.
  캠프는 활동표의 1교시 시작 13:00과 4교시 종료 15:50을 시작/종료 시각으로 사용한다.
- pilot_013: 1·2학기 영상 제출 기간을 각각 마감 한 건으로 두고 시작일은 `periodStartDatetime`이다.
- pilot_014: 검사 전날 식이·운동 주의사항만 체크리스트로 둔다. 월경 중 사전 알림은 해당 학생에게만 적용되는 주의사항으로 보고 제외한다.
- pilot_015: 버스 안전 규칙과 협조 요청은 일반 안내로 보고 items=[]다.
- pilot_016: 동의 표시, 서명, 제출을 하나의 동의서 제출 절차로 보고 체크리스트 1개로 통합한다. 동의 표시와 서명은 detail에 둔다.
- pilot_017: 2학기 수시 상담 기간을 기간 일정 한 건으로 두고 희망자 메일 신청을 체크리스트로 연결한다.
- pilot_018: 체험학습 일정과 함께 9/14~9/16 학급별 사전 안전 교육도 실제 운영 일정으로 보존한다.
- pilot_019: 학급 임원 선출일 8/24만 일정이다. 전교 임원 학급별 활동 기간은 임기 설명으로 제외한다.
- pilot_020: 8/31 CMS 자동이체는 납부 deadline으로 보존하되 별도 행동 요구가 없어 checklistItems=[]다.
  교육여행은 뒷면 일정표의 07:30 집결과 19:40 귀가를 시작/종료 시각으로 사용한다.

평가 실행 결과와 원본 대조 관찰은 `newsletter-pilot-validation.md`의 2차 pilot 섹션에 기록했다.
