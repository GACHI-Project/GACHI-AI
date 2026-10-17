# Pilot 라벨 v3 이전 내역

`data/newsletter-pilot/pilot-labels-v3.json`은 기존 로컬 `labeling_pilot/pilot_gold_labels.json`
10건을 저장소에서 이어서 검수할 수 있도록 이전한 **초안**이다.
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

## 반드시 남겨둔 검수 상태

전체 문서의 실제 OCR 입력과 원본 대조가 아직 완료되지 않았으므로 모두
`annotationStatus=draft`, `inputStatus=pending_actual_ocr`다. 구조 이전을 원본 재검수 완료로
표시하지 않는다. 입력만 연결해도 reviewed로 자동 변경하지 않는다.

- pilot_001: 방과후학교 표의 2024년과 다른 일정의 2025년 충돌은 ambiguous 유지.
- pilot_002: 머리말의 2023년과 하단 발행일 2022년의 충돌을 재검수한다. 요일만으로 연도를 고치지 않는다.
- pilot_004: 향후 저체력 판정을 받은 경우에만 적용되는 교실 참석을 현재 할 일로 둘지 재검수한다.
- pilot_005: 지원금 안내와 실제 신청 요구를 원본에서 구분한다.
- pilot_008: 일반 안전 권고와 실제로 요구한 함께 읽기/시청 과제를 원본에서 구분한다.
- pilot_009: 선출 시기와 개별 보호자의 행동 요구를 구분한다. 임기는 설명 정보로 제외했다.
- pilot_010: 학년별 하교 시각을 행사 시작 시각으로 간주하지 않도록 확인한다.

검수자는 실제 원본과 합의된 라벨 기준을 확인한 뒤 해당 샘플의 `labelVersion`,
`reviewNotes`, `annotationStatus`를 갱신한다. 모델 결과에 맞춰 정답을 바꾸지 않는다.
초안 실행을 위한 `--allow-drafts`는 개발 확인용이며, 확정 정답셋 평가로 보고하지 않는다.

BE 추출 시 기존 pilot ID를 manifest의 sampleId로 사용하면 수동 복사 없이 연결할 수 있다.
HWP 파일은 PDF로 변환한 뒤 같은 ID를 유지한다. 변환 전 이름은 sourceFile 등 메타데이터에 보관한다.
준비 및 평가 명령은 `newsletter-evaluation.md`를 참고한다.
