# 가정통신문 라벨링 기준

본 문서는 사람이 직접 구축하는 정답 데이터와 AI 모델의 판단 기준을 일치시키기 위한 라벨링 가이드라인입니다.

## 기본 원칙

- 원문 근거가 있는 항목만 라벨링한다.
- 날짜는 제공된 `dateCandidates` 중 하나만 선택한다.
- 날짜 후보에 없는 날짜를 사람이 임의로 만들지 않는다.
- 캘린더/알림 생성은 `dateStatus=confirmed` 항목만 대상으로 본다.

## 항목 분류

- `deadline`: 제출, 신청, 납부, 등록, 동의, 회신, 마감처럼 특정 날짜까지 해야 하는 행동
- `schedule`: 행사, 수업, 상담, 체험학습, 설명회, 운영일처럼 실제로 진행되는 일정
- `reminder`: 날짜 없는 구체적 실행 항목 그룹
- 준비물, 제출물, 서명 등 행동은 관련 항목의 `checklistItems`에 넣는다.
- 일반적인 정보와 지속적인 권고는 실행 항목으로 라벨링하지 않는다.
- 날짜 없는 실행 항목은 `missing`, 실제 일정의 불확실한 날짜는 `ambiguous`로 구분한다.
- `type: checklist`인 과거 라벨은 현재 응답 계약과 다르므로 직접 비교하지 않는다.

## 날짜 상태

- `confirmed`: 원문 근거와 `dateCandidates` 중 하나가 명확히 연결된 상태
- `ambiguous`: 날짜 표현은 있지만 후보 매칭이 불확실한 상태
- `missing`: 행동 항목은 있지만 날짜가 없는 상태

## 라벨링 예시

```json
{
  "type": "deadline",
  "title": "체험학습 동의서 제출",
  "evidenceText": "5월 20일까지 체험학습 동의서를 제출해주세요.",
  "selectedDateCandidateId": "dc_1",
  "dateStatus": "confirmed",
  "date": "2026-05-20",
  "target": "parent",
  "actionRequired": true,
  "schoolContext": "보호자가 동의서를 확인하고 제출해야 하는 안내"
}
```
