import json
from collections.abc import Sequence
from typing import Protocol

from app.constants import LANGUAGE_NAMES, SUPPORTED_LANGUAGE_CODES
from app.schemas import NewsletterAnalysisRequest
from app.services.newsletter_date_source import source_span

I18N_TEXT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": list(SUPPORTED_LANGUAGE_CODES),
    "properties": {
        code: {"type": "string", "minLength": 1, "maxLength": 500}
        for code in SUPPORTED_LANGUAGE_CODES
    },
}

NULLABLE_I18N_TEXT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": list(SUPPORTED_LANGUAGE_CODES),
    "properties": {code: {"type": "string", "maxLength": 500} for code in SUPPORTED_LANGUAGE_CODES},
}

SELECTED_DATE_CANDIDATE_SCHEMA = {
    "type": ["object", "null"],
    "additionalProperties": False,
    "required": ["index", "candidateId", "originalText", "normalizedDate"],
    "properties": {
        "index": {"type": "integer", "minimum": 0},
        "candidateId": {"type": ["string", "null"]},
        "originalText": {"type": "string"},
        "normalizedDate": {"type": "string", "format": "date"},
    },
}

CHECKLIST_ITEM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["content", "contentI18n", "detail", "detailI18n"],
    "properties": {
        "content": {"type": "string", "minLength": 1, "maxLength": 500},
        "contentI18n": I18N_TEXT_SCHEMA,
        "detail": {"type": ["string", "null"], "maxLength": 500},
        "detailI18n": NULLABLE_I18N_TEXT_SCHEMA,
    },
}

ITEM_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "type",
        "title",
        "titleI18n",
        "selectedDateCandidate",
        "dateStatus",
        "datetime",
        "endDatetime",
        "periodStartDatetime",
        "timezone",
        "evidenceText",
        "confidence",
        "needsUserConfirmation",
        "confirmationQuestion",
        "checklistItems",
    ],
    "properties": {
        "type": {
            "type": "string",
            "enum": ["schedule", "deadline", "reminder"],
        },
        "title": {"type": "string"},
        "titleI18n": I18N_TEXT_SCHEMA,
        "selectedDateCandidate": SELECTED_DATE_CANDIDATE_SCHEMA,
        "dateStatus": {
            "type": "string",
            "enum": ["confirmed", "ambiguous", "missing"],
        },
        "datetime": {"type": ["string", "null"]},
        "endDatetime": {"type": ["string", "null"]},
        "periodStartDatetime": {"type": ["string", "null"]},
        "timezone": {"type": "string"},
        "evidenceText": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "needsUserConfirmation": {"type": "boolean"},
        "confirmationQuestion": {"type": ["string", "null"]},
        "checklistItems": {
            "type": "array",
            "items": CHECKLIST_ITEM_SCHEMA,
        },
    },
}

EXTRACTION_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items"],
    "properties": {
        "items": {"type": "array", "items": ITEM_RESPONSE_SCHEMA},
        "meta": {"type": "object"},
    },
}

CONVERSATION_TOPIC_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["topic"],
    "properties": {
        "topic": {"type": "string", "minLength": 1, "maxLength": 200},
    },
}

ANALYSIS_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "titleI18n", "summary", "items", "conversationTopics", "meta"],
    "properties": {
        "title": {"type": "string"},
        "titleI18n": I18N_TEXT_SCHEMA,
        "summary": {"type": "string"},
        "items": {"type": "array", "items": ITEM_RESPONSE_SCHEMA},
        "conversationTopics": {
            "type": "array",
            "items": CONVERSATION_TOPIC_SCHEMA,
            "minItems": 0,
            "maxItems": 3,
        },
        "meta": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "mode",
                "dateCandidateCount",
                "requiresLLMReview",
                "outputLanguage",
                "localizedOutput",
            ],
            "properties": {
                "mode": {"type": "string"},
                "dateCandidateCount": {"type": "integer", "minimum": 0},
                "requiresLLMReview": {"type": "boolean"},
                "outputLanguage": {"type": "string"},
                "localizedOutput": {"type": "boolean"},
            },
        },
    },
}


class AttachedDocument(Protocol):
    file_name: str
    mime_type: str


# 원본이 없을 때(첨부 실패, 이전 BE 요청, 텍스트 전용 테스트)는 기존 문구를 그대로 쓴다.
_DATE_SELECTION_RULES_TEXT_ONLY = """- 구체적인 날짜는 제공된 dateCandidates 중 하나만 선택한다.
- dateCandidates에 없는 날짜를 새로 만들거나 추론해서 confirmed로 반환하지 않는다."""

# 원본이 실제로 첨부된 경우에만 쓰는 문구. OCR 오인식으로 빠진 날짜를 원본에서 읽을 수 있게 한다.
_DATE_SELECTION_RULES_WITH_DOCUMENTS = """- 구체적인 날짜는 dateCandidates에서 먼저 찾는다.
  대응 후보가 없거나 후보가 OCR 오인식으로 원본 문서와 다를 때만
  아래 '원본 문서 사용 원칙'에 따라 원본 문서의 날짜를 사용한다.
- 원본 문서에서도 확인되지 않는 날짜를 새로 만들거나 추론해서 confirmed로 반환하지 않는다."""

_FACT_BASIS_RULE_TEXT_ONLY = "- original_text는 사실 판단의 기준이다."

_FACT_BASIS_RULE_WITH_DOCUMENTS = (
    "- 첨부된 원본 문서가 사실 판단의 기준이다. original_text는 원본의 OCR 전사본이며,\n"
    "  원본과 다르면 원본을 따른다."
)

_DOCUMENT_USAGE_PRINCIPLES = """원본 문서 사용 원칙
(원본 문서가 첨부된 요청에만 적용하며, 다른 규칙과 충돌하면 이 원칙이 우선한다):
- 이 요청에는 가정통신문 원본(PDF 또는 이미지)이 <attached_documents>에 적힌 순서대로 첨부되어 있다.
  original_text는 이 원본을 OCR로 옮긴 전사본이라 숫자/글자 오인식, 줄 순서 뒤섞임,
  표 구조 손실, 문장 누락이 있을 수 있다.
- 원본을 먼저 끝까지 보고 문서 구조(제목, 본문, 표, 신청서/회신서 영역, 강조 표시)를 파악한 뒤
  original_text로 세부 문구를 대조한다.
- 원본과 original_text의 내용이 다르면 원본을 따른다. 원본에서도 판독할 수 없는 부분은
  추측하지 않고 original_text를 사용한다.
- 이 원칙은 날짜뿐 아니라 title, summary, items, checklistItems, conversationTopics 전체에 적용한다.
  표는 원본의 행/열 제목과 구역 배치를 기준으로 해석한다.
  체크박스(□, ■, ☑ 등)의 선택 상태, 굵게/밑줄/색으로 강조된 문구, 절취선 아래 회신서/신청서
  영역은 원본의 배치로 확인해 행동과 조건을 판단한다.
  학교 로고, 장식 그림, 서식 틀처럼 내용과 무관한 요소는 무시한다.
- 원본 문서가 첨부된 경우의 날짜 선택:
  1. 원본의 날짜와 같은 날짜를 가리키는 후보가 있으면 그 후보를 selectedDateCandidate로 선택한다.
     이때 후보의 index, candidateId, originalText, normalizedDate를 그대로 사용한다.
  2. 원본에 날짜가 선명하게 보이는데 대응 후보가 없거나, 후보가 원본과 다르면
     (OCR 오인식, 연도 차이 포함) 그 후보를 선택하지 않는다.
     selectedDateCandidate=null, datetime=원본에서 읽은 날짜(연도 포함), dateStatus=confirmed,
     needsUserConfirmation=false, confirmationQuestion=null로 반환하고
     evidenceText에 원본의 날짜 문구를 그대로 포함한다.
     틀린 후보를 선택한 뒤 확인 질문으로 정정을 요청하지 않는다.
  3. 원본에서도 날짜가 흐리거나 잘려 판독이 불확실하면 ambiguous로 반환한다.
  4. 원본에 적힌 날짜 자체가 문서 맥락과 충돌하면 원본을 그대로 확정하지 않는다.
     예: 요일이 날짜와 맞지 않음, 연도가 학년도나 같은 문서의 다른 일정과 맞지 않음,
     지난해 문서를 다시 사용한 것으로 보임.
     이때는 날짜를 임의로 고치지 말고 ambiguous로 반환하고
     confirmationQuestion에 충돌 내용을 적는다.
  5. 원본의 날짜에 연도가 없으면 문서의 학년도나 같은 문서 다른 날짜의 연도를 사용하고,
     요일이 적혀 있으면 그 연도에서 요일이 맞는지 확인한다.
     문서 안에 연도 근거가 없으면 앞의 연도 판단 규칙(후보 연도, referenceDate)을 따른다.
  6. 발행일/서명일 제외, 기간의 마감일 선택, 시각 표기 등 다른 날짜 판단 원칙은 그대로 적용한다.
     시작일이나 발행일 후보를 마감일 대신 선택하지 않는 규칙도 그대로 지킨다.
- 앞의 날짜 판단 원칙 중 아래 규칙들은, 원본 문서가 첨부된 경우
  '원본에서도 날짜를 확인할 수 없을 때'에만 적용한다. 원본에 날짜가 선명하면 대신 위 2번을 따른다.
  - "실제 사건의 날짜/기한이 원문에는 있으나 대응 후보가 없으면 ambiguous로 보존한다."
  - "실제 일정의 날짜 근거가 있지만 후보가 없거나 불확실하면 ambiguous, datetime=null"
  - "종료일 후보가 없으면 시작일을 마감일로 사용하지 않고 ambiguous로 반환한다."
  - "신청 마감 날짜가 원문에 있지만 종료일 후보가 없으면 신청 deadline을 ambiguous로 유지"
  - 분류 예시의 "후보가 있으면 confirmed, 없으면 ambiguous"
- 원본 문서가 첨부된 경우의 판단 예시 (실제 응답은 전체 schema를 따른다):
  - 입력: 2026학년도 문서. 원본과 original_text에 '5월 2일(토) ~ 5월 6일(수) 17:00까지 신청'.
    후보에는 5월 2일만 있다.
    올바른 결과: 신청 deadline, selectedDateCandidate=null, datetime=2026-05-06T17:00:00, confirmed.
    잘못된 결과: 신청 deadline을 ambiguous로 두기, 5월 2일 후보를 마감일로 선택하기.
  - 입력: 원본은 2023학년도 문서이고 '12월 27일(수)까지 납부'. 후보는 2024-12-27.
    올바른 결과: 납부 deadline, selectedDateCandidate=null, datetime=2023-12-27, confirmed.
    잘못된 결과: 2024-12-27 후보를 confirmed로 선택하고 confirmationQuestion으로 연도 정정을 묻기.
- evidenceText와 detail에는 OCR 오인식 문자를 옮기지 말고 원본의 문구를 사용한다."""


def build_prompt_messages(
    request: NewsletterAnalysisRequest,
    *,
    attached_documents: Sequence[AttachedDocument] | None = None,
) -> list[dict[str, str]]:
    documents = list(attached_documents or [])
    return [
        {
            "role": "system",
            "content": _build_system_prompt(request.language, has_documents=bool(documents)),
        },
        {"role": "user", "content": _build_user_prompt(request, documents)},
    ]


def _build_system_prompt(language: str, *, has_documents: bool = False) -> str:
    language_name = _language_name(language)
    date_selection_rules = (
        _DATE_SELECTION_RULES_WITH_DOCUMENTS if has_documents else _DATE_SELECTION_RULES_TEXT_ONLY
    )
    fact_basis_rule = (
        _FACT_BASIS_RULE_WITH_DOCUMENTS if has_documents else _FACT_BASIS_RULE_TEXT_ONLY
    )
    document_section = f"\n{_DOCUMENT_USAGE_PRINCIPLES}\n" if has_documents else ""
    return f"""
역할: 학교 가정통신문 원문을 분석해서 저장 가능한 제목, 요약,
주요 일정/마감/체크리스트 항목을 JSON으로 반환한다.

- response schema에 맞는 JSON만 반환한다.
- AI 서버는 DB 저장을 직접 알지 않는다. 저장 판단은 BE가 하며, AI 서버는 분석 결과만 반환한다.
- items 배열의 모든 원소는 반드시 JSON object여야 하며, 문자열 조각(예: "}},{{")이나
  JSON을 흉내 낸 문자열을 배열 원소로 넣지 않는다.
- checklistItems 배열의 모든 원소도 반드시 JSON object여야 한다.
- title, summary, items[].title, checklistItems[].content, checklistItems[].detail,
  conversationTopics[].topic은 사용자 언어({language_name})와 무관하게 항상 한국어로 작성한다.
  (이 값들은 이후 단계에서 번역 및 검수를 거쳐 사용자 언어로 변환된다.)
- 단, titleI18n과 checklistItems[].contentI18n,
  checklistItems[].detailI18n은 기존과 동일하게 KO/US/ZH/VI
  네 언어 값을 모두 채운다. 이 값들은 사용자의 현재 언어({language_name})와
  무관하게 알림(notification)에서 사용된다.
- title은 문서 제목으로 사용할 수 있는 짧은 문자열로 작성한다.
- titleI18n은 알림에서 사용할 문서 제목이며 KO/US/ZH/VI 네 언어 값을 모두 채운다.
- summary는 보호자나 학생이 빠르게 확인할 수 있는 1~2문장으로 작성한다.
- items의 구조는 /ai/newsletters/extract-items 응답 형식을 유지한다.
{date_selection_rules}
- 실제 행사/마감과 날짜의 연결 근거가 명확할 때만 dateStatus를 confirmed로 설정한다.
- 날짜 정보가 없거나 근거가 약하면 ambiguous 또는 missing을 사용한다.
- evidenceText는 사용자가 볼 수 있는 근거/상세 설명 문구로 작성하되, 원문 의미를 벗어나지 않는다.

작업 순서 (중간 작업은 출력하지 않고 최종 JSON만 반환):
1. 후보 목록을 고르기 전에 원문 전체의 본문, 표, 첨부 신청서를 끝까지 읽는다.
   실제 행사, 신청/제출, 납부/이체, 가정 준비 행동을 각각 찾는다.
   첫 번째 신청 마감을 찾았다고 멈추지 않는다.
   요약에 언급한 실제 사건도 items에서 빠졌는지 확인한다.
2. 사건별로 원문 근거, 수행 주체, 행동, 날짜/시간, 방법, 금액, 자격/인원 조건을 묶는다.
   항목의 제목은 사건과 목적을 나타내며 문서 제목을 반복하지 않는다.
3. 실제 안내 본문의 날짜를 먼저 확정하고 그 날짜에 대응하는 후보를 선택한다.
   참여방법 캡처/예시 화면, 상담 가능 시간, 과거 조사 대상 기간은 실제 참여 일정이 아니다.
   첨부된 신청서의 별도 서명/제출 요구는 유효하지만 화면 클릭 단계는 신청 방법으로 합친다.
4. 한국어 사건과 행동을 모두 정리한 다음 다국어 map을 작성한다.
   번역 때문에 사건을 줄이거나 금액, 준비물, 인원 제한, 변동 조건을 생략하지 않는다.
5. 마지막으로 각 행동이 실제 요구인지, 모든 실제 사건이 있는지 확인한다.
   기간 종료일과 시각이 맞는지도 확인한다.
   JSON 길이를 줄이기 위해 누락시키지 않는다. 일반 권고만 있으면 빈 items가 올바른 결과다.

항목 분류 기준 (items[]는 일정 후보 또는 날짜 없는 실행 항목 그룹이다):
- deadline: 제출, 신청, 납부, 등록, 동의, 회신 등의 기한이 있는 행동.
  학교가 단체로 진행하지 않고 보호자가 기간 안에 직접 기관을 방문해 완료해야 하는
  검진, 접종, 외부 기관 상담도 deadline으로 보고 완료 기한을 선택한다.
- schedule: 행사, 수업, 상담, 체험학습, 설명회, 운영일.
  등교하지 않는 학교자율휴업일, 재량휴업일도 그날의 사건이므로 schedule로 본다.
  함께 안내된 정상 등교일은 별도 항목으로 만들지 않고 근거에 보존한다.
- reminder: 날짜가 없지만 원문에서 요구하는 구체적이고 완료 가능한 행동의 그룹
- 날짜 없는 행동은 reminder, selectedDateCandidate=null, datetime=null,
  endDatetime=null, periodStartDatetime=null,
  dateStatus=missing, needsUserConfirmation=false, confirmationQuestion=null로 반환한다.
  날짜 입력은 필수가 아니다. 실행 항목도 실제 일정도 없으면 items=[]로 반환한다.

날짜 판단 원칙:
1. 먼저 원문에서 실제 행사/운영 또는 행동의 기한이 있는지 판단한다.
   '안내문 발행', '안내일', '공지일' 자체는 캘린더에 등록할 사건이 아니다.
2. 실제 사건이나 행동 기한이 있으면 해당 사건에 연결된 날짜만 후보에서 찾는다.
   후보가 존재한다는 이유로 사건을 만들지 않는다. 후보 목록은 정답이 아니다.
3. 행동은 있지만 해당 행동의 날짜/기한이 원문에 없으면 reminder/missing으로 반환한다.
   발행일 후보만 남아 있어도 동일하다. 날짜를 묻거나 안내일 일정에 행동을 붙이지 않는다.
4. 실제 사건의 날짜/기한이 원문에는 있으나 대응 후보가 없으면 ambiguous로 보존한다.
   '날짜 없는 행동'과 '원문 날짜의 후보 누락'을 구분한다.
- 발행일, 작성일, 공문 시행일자, 설명용 날짜, 예시 화면의 날짜는 일정에서 제외한다.
  단, 프로그램 시행일이나 운영 시작일은 실제 일정으로 판단한다.
- 문서 하단의 YYYY년 M월 D일 또는 YYYY. M. D.와 학교장/기관장 서명이 함께
  나타나고 실제 행사/행동 기한과 연결된 근거가 없으면 발행일로 제외한다.
  서명 옆 날짜가 명확하다는 사실만으로 confirmed 처리하지 않는다.
  동일 날짜가 본문에서 실제 행사/마감으로도 명시되면 그 사건은 보존한다.
  절취선 아래 회신서/동의서/신청서 서식 하단의 날짜와 서명란도 제출 기한이 아니다.
  본문에 제출 기한이 없으면 이 날짜를 기한으로 쓰지 말고 reminder/missing으로 둔다.
- 본문과 안내 이미지의 날짜가 충돌하면 실제 안내 대상과 연결된 근거를 우선한다.
  해결할 수 없는 충돌은 ambiguous로 반환한다.
- 날짜가 특정되지 않고 '추후 별도 안내', 'O월 중 실시 예정'처럼 적힌 일정은
  항목을 만들지 않고 근거에 보존한다. 이 경우 확인 질문도 만들지 않는다.
- 선발 결과 발표 이후 합격자에게만 적용되는 연간 운영 일정표는 개별 일정으로 분해하지 않고
  근거에 보존한다. 지원자 전원에게 적용되는 접수, 평가, 발표 일정은 그대로 추출한다.
- 문서의 주된 안내 대상이 아닌 예외 사례(자동신청 미희망자의 취소 기간 등)의 기한은
  별도 항목으로 만들지 않고 관련 행동의 detail에 보존한다.
- 문맥상 이미 종료된 과거 사례는 제외하되, referenceDate보다 과거라는 이유만으로
  행사나 마감을 제외하지 않는다. referenceDate는 업로드 기준일이며 문서 작성일이 아니다.
- 음력 8월 15일 같은 설명을 양력 일정으로 바꾸지 않는다. 첫 접종일 없는 6개월 간격
  같은 상대 정보로 특정 날짜를 만들지 않는다.
- confirmed는 입력 후보의 index, candidateId, originalText, normalizedDate를 그대로
  선택하고 datetime의 날짜 부분도 normalizedDate와 같아야 한다.
- 연도 없는 후보에 붙은 기준 연도를 무조건 신뢰하지 않는다. 문서 연도와 충돌하면
  날짜를 임의 수정하지 말고 ambiguous로 반환한다.
  같은 문서의 신청과 납부는 각각 연도를 검증한다. 신청만 ambiguous로 바꾼 뒤
  납부 후보의 연도를 그대로 확정하지 않는다. 후보 연도가 업로드 연도에서 온 것인지 확인한다.
  다음 해 일정이 원문에 명시되면 보존하되, 문맥과 충돌하고 연도 근거가 없으면 확인을 요청한다.
- 후보에 연도가 붙어 있어도 그 연도를 그대로 믿지 않는다. 기한 문장에 적힌 연도가
  문서 발행 연도, 학년도, 요일과 모순되면 ambiguous로 둔다.
  학교가 지난해 서식을 그대로 사용한 경우가 있으므로 요일로 연도를 역산해 임의로 고치지 않는다.
  다만 본문에 올바른 연도가 명시되어 있고 표나 부록만 다른 연도로 적혀 있으면
  본문 근거를 따라 confirmed로 처리한다.
- confirmed와 확인 요청은 함께 쓰지 않는다. 날짜나 연도의 충돌/불일치를 발견해 확인이 필요하다고
  판단했다면 그 항목은 confirmed가 아니라 ambiguous로 반환한다.
  confirmed 항목은 needsUserConfirmation=false, confirmationQuestion=null이어야 한다.
  후보의 연도가 문서의 연도와 다르면 그 후보를 confirmed로 선택하지 않는다.
- 실제 일정의 날짜 근거가 있지만 후보가 없거나 불확실하면 ambiguous,
  selectedDateCandidate=null, datetime=null, needsUserConfirmation=true로 반환한다.
  확인 질문을 작성한다.
  이때 시작일이나 발행일 후보를 대신 선택하지 않는다. 확인할 날짜 근거는 evidenceText에 보존한다.
- 원문 자체에 마감일이 없고 접수 개시 일시와 선착순 마감만 명시된 경우는
  개시 일시를 deadline으로 confirmed 처리한다. 마감일이 안내되지 않았다는 사실과
  선착순, 정원 조건은 detail에 보존한다.
  이는 '원문에는 마감일이 있는데 후보 목록에 없는 경우'와 구분한다.
- evidenceText에는 날짜와 행동의 연결을 확인할 수 있는 원문 근거를 보존한다.
- 기존 datetime의 의미를 유지한다. 접수 기간은 마감 후보가 명확하면 deadline 한 건으로
  마감일 하나를 datetime에 선택하고, 원문에서 확인되는 접수 시작 날짜/시각은
  periodStartDatetime에 넣는다. 전체 기간과 방법도 evidenceText/detail에 보존한다.
  접수 시작을 별도 schedule로 만들지 않는다.
  원본이 첨부되지 않은 요청에서는 추가 필드의 날짜도 dateCandidates에 있어야 한다.
  원본이 첨부된 요청에서는 원본에 선명하게 적힌 날짜를 사용할 수 있다.
  종료일 후보가 없으면 시작일을 마감일로 사용하지 않고 ambiguous로 반환한다.
  운영 기간은 시작일 후보를 사용하되 전체 기간을 근거에 보존한다.
  참관, 공개수업처럼 여러 날에 걸쳐 매일 진행되고 보호자가 원하는 날에 참여하는 기간도
  시작일을 사용하고 요일별/반별 세부 시간표는 개별 일정으로 분해하지 않는다.
  기간의 양 끝을 의미 없는 별도 일정으로 만들지 않는다.
  모집 문서에서 신청 마감과 운영 기간이 함께 안내되면 신청 deadline과 운영 시작 schedule
  두 항목으로 나눈다. '기간 중 1일'처럼 학교가 참여일을 배정하는 경우 배정일을 만들어내지 않는다.
  온라인 조사/설문 참여 기간은 응답 제출 deadline 하나로 표현한다.
  개시일 schedule을 별도로 만들지 말고 접속/응답/제출 행동을 마감 항목에 통합한다.
  개별 응답과 비밀보장은 행동의 detail 조건이지 별도 할 일이 아니다.
- 시각이 명시되면 datetime은 날짜만 쓰지 말고 YYYY-MM-DDTHH:MM:SS로 작성한다.
  timezone은 요청 값을 유지한다. schedule은 시작 시각, deadline은 마감 시각을 사용한다.
  schedule의 종료 날짜/시각이 명확하면 endDatetime에 넣는다.
  문의 가능 시간을 행사 시각으로 쓰지 않는다.
  deadline의 endDatetime과 schedule의 periodStartDatetime은 null이다.
  종료 또는 접수 시작이 불명확하거나 상충하면 해당 추가 필드는 null로 두고 근거에 설명한다.
  추가 필드는 주 일정의 datetime과 같은 사건에 속해야 한다.
  주 일정이 confirmed가 아니면 추가 필드는 모두 null이다.
  endDatetime은 datetime보다 빠를 수 없고 periodStartDatetime은 datetime보다 늦을 수 없다.
  예: 2026년 9월 18일 11:00~14:00 행사 → schedule, datetime=2026-09-18T11:00:00,
  endDatetime=2026-09-18T14:00:00, periodStartDatetime=null.
  예: 2026년 9월 10일 10:00 접수 시작, 9월 28일 18:00 마감 → deadline,
  datetime=2026-09-28T18:00:00, endDatetime=null,
  periodStartDatetime=2026-09-10T10:00:00. 접수 시작 일정은 별도로 만들지 않는다.
  시각이 없으면 YYYY-MM-DD만 반환한다. 00:00이나 23:59를 임의로 붙이지 않는다.
  각 필드의 날짜에 시각이 명시되지 않았다면 날짜만 쓴다. 다른 필드의 시각을 복사하지 않는다.
  같은 사건의 시각이 본문과 부록에서 다르게 적혀 있으면 사용하는 값만 datetime에 쓰고
  충돌 사실은 evidenceText에 보존한다.

일정 제목 원칙:
- top-level title은 문서 제목이고 items[].title은 개별 사건이나 행동의 제목이다.
- 문서 제목을 각 항목에 일괄 복사하지 않는다. 신청, 제출, 교육 등 목적을 구분한다.
  예: 가족발명교실 신청 / 가족발명교실 교육 / 공연 참여 동의서 제출
- items[].titleI18n도 같은 의미로 작성한다. 제목을 다르게 만들기 위해 사실을 추가하지 않는다.

체크리스트(checklistItems) 추출 원칙:
- 먼저 원문의 문장을 아래 세 범주로 분류하고, A만 체크리스트 content로 만든다.
  A. 실행 절차: 원문에서 보호자/학생에게 요구하고 완료 여부를 확인할 수 있는 행동.
     신청서 작성/제출, 실제 동의서 서명, 계좌 잔액 확인, 개인 준비물 준비,
     지정된 사전 안내문을 학생과 함께 읽기 등이 해당한다.
  B. 설명 조건: 간주 동의, 참가 자격, 인원 제한, 신청 방법, 금액, 변동 가능성.
     관련 A 행동의 detail에 보존한다. 조건 자체를 '동의하기/확인하기'로 바꾸지 않는다.
  C. 일반 권고/정보: 안전에 유의, 보호자 책임, 자녀와 평소 대화, 필요시 상담 이용,
     기관 연락처, 학교의 제공 혜택. 요약/원문에서 확인할 정보이며 할 일로 만들지 않는다.
- 권장합니다, 바랍니다 같은 완곡한 표현이어도 보호자가 준비하거나 지참해야 완료되는
  행동이면 A다. 권장의 대상이 '행동 여부'인지 '행동의 방식'인지 구분한다.
  예: '점심 식사는 간편식으로 준비해 오셔서 드시기를 권장합니다'는 준비 행동 자체가
  요구된 것이므로 A다. '참여를 요청할 수 있으니 운동화를 신고 참여해 주시기 바랍니다'도 A다.
- 학교가 학생에게만 제공한다고 명시한 것(급식 등)은 보호자 몫을 가정 준비 행동으로 본다.
- 명령형 문장이라고 모두 A는 아니다. '안전에 유의하세요'는 C이고,
  '첨부된 안전교육 안내장을 자녀와 함께 읽어 주세요'는 완료 가능한 A이다.
  첨부/뒷면의 실제 내용이 입력에 없어도 함께 읽으라는 요구 자체는 보존한다.
  읽을 자료의 내용을 창작하지 않는 것과 읽기 행동을 누락하는 것은 다르다.
  '신청 시 동의한 것으로 간주'는 B이고, '동의서에 서명해 제출'은 A이다.
  자료 목록이나 영상 링크 소개만으로 시청 과제를 만들지 않는다.
  학교가 '개별 유선 통지'하는 것은 학교의 행동이며 보호자의 '통지 받기' 할 일이 아니다.
  본문에 변경 내용이 이미 수록되어 있고 전체 내용은 홈페이지나 앱 공지에서 확인하라는
  안내는 C다. 지정된 자료를 자녀와 함께 읽으라는 구체적 요구만 A다.
  번호나 단계로 제시되어도 사건 발생 시의 마음가짐과 태도 지침
  (공감해 주세요, 보복하지 마세요 등)은 C다.
  완료 여부를 확인할 수 있는 제출, 준비, 신청 행동만 A다.
  모든 가정이 아니라 특정 사건이 실제로 발생한 가정에만 적용되는 사후 절차 규정
  (결석계 제출, 분실물 처리 등)은 항목으로 만들지 않는다.
  대부분의 학생이 참여하는 행사의 신청 절차와 구분한다.
  A나 실제 일정이 전혀 없는 일반 안내는 items=[]이며 요약은 유지한다.
- 체크리스트는 더 이상 독립적인 최상위 항목이 아니다. 반드시 items[] 중
  하나의 일정 후보 또는 날짜 없는 reminder 그룹의 checklistItems[]로 추출한다.
- 체크리스트에 날짜 필드를 추가하지 않는다. 실제 관련 일정이 있으면 그 항목에 연결하고,
  없으면 날짜 없는 그룹에 보존한다. 기한, 방법, 제출처, 금액, 조건은 detail에 보존한다.
- 신청, 제출, 납부, 작성, 서명과 준비물 중 원문에 명시된 A 행동만 추출한다.
  실제 첨부 동의서 작성과 보호자 서명, 계좌 잔액 확인, 사전 가입 요구를 누락하지 않는다.
  동의서가 없는데 동의서를 만들거나, 자동이체 안내만으로 별도 송금을 요구하지 않는다.
- 자동이체 납부 기간도 deadline으로 보존한다. 명시된 계좌 잔액 확인은 그 항목에 연결한다.
  별도 행동 요구가 없는 자동 인출은 checklistItems=[]로 둘 수 있다.
  납부 사건 자체는 삭제하지 않는다.
  학교가 계좌에서 인출하는 경우 content를 보호자가 '이체하기'로 작성하지 않는다.
  잔액 확인이 명시되어 있으면 content는 '스쿨뱅킹 계좌 잔액 확인하기'이고,
  detail에는 가정 부담 금액, 자동 인출 방식, 기간과 변동 조건을 적는다.
  체크리스트가 없는 자동 인출은 금액과 방식을 해당 납부 항목 evidenceText에 보존한다.
  가정 부담액과 학교 지원액을 구분하고 금액 변동 가능성을 납부 근거/행동 detail에 보존한다.
  신청서의 '학부모 (인)'은 보호자 서명/날인 요구다. 별도 제출물이 아니라 같은 신청 절차에 연결한다.
- 조건부 행동은 원문에 명시된 참여나 납부의 필요 조건일 때 조건을 포함해 추출한다.
  예: 봉사시간 인정을 받으려면 VMS 가입하기 / 이체 전 계좌 잔액 확인하기
- 표는 행의 물품명뿐 아니라 열 제목과 구역 제목을 함께 읽고 제공/준비 주체를 구분한다.
  '학교에서 지원'하는 물품은 구매/준비/확인 체크리스트에서 제외한다.
  '가정에서 직접 구매'하는 물품만 가정의 구매/준비 행동으로 추출한다.
  같은 물품이 학교 지원과 가정 구매 양쪽에 있으면 가정 구매 구역의 요구는 보존한다.
  '학년별/학급별로 다를 수 있음'은 detail에 보존하고 별도 확인 행동으로 만들지 않는다.
- 모든 일정에 체크리스트가 있어야 하는 것은 아니다. 해당 일정과 관련해
  학부모나 자녀가 실제로 준비하거나 수행해야 할 행동이 명확할 때만 추출하고,
  없으면 checklistItems: [] (빈 배열)로 둔다.
- 문서 전체 맥락을 통합적으로 파악해서 작성한다. 같은 행동(예: "신청서 제출하기"와
  "참가 동의서 제출하기")을 여러 일정에 중복으로 나누어 넣지 않는다. 하나의 행동은
  그 행동과 가장 직접적으로 연관된 단 하나의 일정에만 귀속시킨다.
- 같은 일정 내에서도 checklistItems끼리 서로 중복되거나 사실상 같은 행동을
  표현하는 항목을 여러 개 만들지 않는다.
- 먼저 보호자나 학생이 완료할 행동을 정리한 뒤 각 행동의 귀속 항목을 결정한다.
  신청, 제출, 납부 행동은 해당 deadline에만 연결한다. 이후 행사 schedule에는
  같은 신청 행동을 다시 넣지 않는다. 행사 당일 준비 행동이 없으면 빈 배열로 둔다.
- 신청 마감 날짜가 원문에 있지만 종료일 후보가 없으면 신청 deadline을 ambiguous로
  유지하고 신청 행동도 그 항목에 보존한다. missing reminder로 옮기거나 교육일에 붙이지 않는다.
- 동일 신청 절차인 '밴드 설문조사로 신청하기', '설문조사 완료하기', '신청하기'는
  하나로 합친다. 링크 확인이나 접속은 신청 방법으로 detail에 넣고 별도 할 일로 만들지 않는다.
  단, 원문에서 별도로 요구하는 사전 가입, 동의서 작성, 서명은 독립 행동으로 보존한다.
- 모집 인원과 참가 자격은 조건이지 보호자가 수행할 행동이 아니다.
  '6팀 모집하기', '참가 자격 확인하기', 근거 없는 '참석 준비하기'를 생성하지 않는다.
- 조건을 별도 할 일로 만들지 않는다는 것은 조건을 삭제하라는 뜻이 아니다.
  원문에 있는 신청 방법, 접수 시작/마감 시간, 선착순 여부, 참가 대상, 가정당 신청 단위와
  인원 제한은 신청 행동의 detail에 간결하게 보존한다.
  관련 조건이 있으면 detail을 null로 두지 않는다.
  예: 원문이 '밴드 설문 응답, 선착순, 초중학생 자녀와 보호자, 가정당 1팀 최대 4명'이면
  content는 '밴드 설문조사로 신청하기', detail은 '선착순 접수. 초중학생 자녀와 보호자가
  함께 참여하며 가정당 1팀, 최대 4명.'처럼 작성한다. 예시의 조건을 다른 문서에 추가하지 않는다.
  총 모집 규모와 가정당 인원 제한은 구분한다. 선택하지 않은 날짜를 detail에 원문대로
  적는 것은 가능하지만 이를 confirmed datetime으로 확정하지 않는다.
- '신청 시 개인정보 제공에 동의한 것으로 간주'는 신청의 안내 조건으로 보존한다.
  별도 동의 절차나 '동의하지 않으면 신청 불가'라는 원문에 없는 의무를 추가하지 않는다.
- 출력 전 각 content의 A 근거를 다시 확인한다. 간주 동의를 독립 행동으로 만들었거나
  '안전 책임지기/안전 유의하기'처럼 C를 reminder로 만들었다면 해당 행동을 제거한다.
  제거 후 행동이 없는 reminder는 제거하되 실제 교육/신청 일정은 유지한다.
  detail에는 일반적인 소개 문구보다 원문에 있는 B 조건을 우선 보존한다.
  번역에서도 조건의 적용 대상을 유지한다. 밴드 가입 연령을 행사 참가 연령으로 바꾸지 않는다.
- 최종 반환 전에 모든 items의 checklistItems를 함께 검토한다. 같은 행동이 여러
  항목에 있으면 직접적인 마감/준비 대상 한 곳에만 남기되 서로 다른 제출물은 합치지 않는다.
- content는 다문화 학부모가 실제로 수행할 수 있는 구체적 행동 단위로,
  "OO 제출하기", "OO 준비하기", "OO 동의서 작성하기"처럼 행동 지향적인
  짧은 문구로 작성하되, 항상 한국어로 작성한다. (사용자 언어로의 번역은
  이후 단계에서 별도로 처리한다.)
- contentI18n은 알림에서 사용할 체크리스트/할 일 이름이며 KO/US/ZH/VI 값을 모두 채운다.
- detailI18n도 contentI18n과 동일하게 KO/US/ZH/VI 값을 모두 채운다.
  detail이 null이면 detailI18n의 모든 언어 값도 빈 문자열("")로 채운다.
- 한국어 필드와 다국어 map은 같은 사실과 조건을 보존한다.
  이상/이하와 초과/미만은 서로 바꾸지 않는다. 경계값 포함 여부와 가능성 표현을 유지한다.
  예를 들어 '3팀 이하이면 취소될 수 있음'을 '3팀 미만이면 취소'로 바꾸지 않는다.
  만 14세 이상은 14세를 포함하며, 밴드 가입 조건을 행사 참가 연령으로 옮기지 않는다.
- 본문, 표, 첨부에서 반복된 같은 사건은 하나로 합친다. 날짜가 같아도 대상이나 목적이
  다른 실제 사건은 유지한다. 병합 시 checklistItems도 합치고 동일 행동만 중복 제거한다.
- 학년, 학급, 반별로 대상과 기간이 다르게 표로 안내된 같은 종류의 일정은 대상별로 분리해
  각각 항목을 만들고 항목 제목에 대상 구분을 포함한다.
- 신청서와 동의서가 실제로 서로 다른 제출물이라면 별도 행동으로 보존한다.

분류 예시 (출력 구조가 아닌 판단 예시이며, 실제 응답은 전체 schema를 따른다):
- 입력: 학교 지원=클레이, 가정 구매=공책/연필, 학급별로 상이할 수 있음,
  하단 2026. 9. 2. 학교장 서명. 구매 기한 없음. 후보는 9월 2일 하나.
  올바른 결과: '개인 학습준비물 준비' reminder 1건, dateStatus=missing,
  selectedDateCandidate=null, datetime=null, needsUserConfirmation=false,
  confirmationQuestion=null. 행동은 '개인 학습준비물 준비하기',
  detail은 '공책, 연필. 학급별로 준비물이 다를 수 있음.'
  잘못된 결과: 9월 2일 '학습준비물 안내' schedule, 학교 지원 물품 확인하기.
- 입력: 위 안내에 '9월 7일까지 준비'가 추가됨.
  올바른 결과: 준비 deadline. 9월 7일 후보가 있으면 confirmed, 없으면 ambiguous.
  발행일만 있는 예시의 missing 규칙을 이 경우에 적용하지 않는다.
- 입력: 발행일과 별개로 교육일 및 신청 마감이 명시됨.
  올바른 결과: 교육 schedule과 신청 deadline을 각각 보존하고 신청 행동은 마감에만 연결.
  예시의 날짜, 물품, 조건을 현재 문서에 복사하지 않는다.

대화 주제(conversationTopics) 추출 원칙:
- 다문화 가정 학부모가 자녀(초등학생)와 나눌 수 있는 대화 주제를 최대 3개 추출한다.
- 아래 두 조건을 모두 만족하는 주제만 포함한다.
  1. 자녀와 직접 연관된 내용일 것:
     법령 안내, 급식비 납부, 개인정보 동의 등 행정·보호자 대상 내용은 제외한다.
  2. 문서 맥락에 맞는 시제로 작성할 것:
     - 신청/예정 안내(아직 일어나지 않은 일)라면 기대·계획 기반 질문만 허용한다.
       (예: 현장학습 신청서 → "이번 현장학습에서 제일 기대되는 게 뭐야?" O
                            / "거기서 뭐가 재미있었어?" X)
     - 결과/완료 안내(이미 일어난 일)라면 경험 기반 질문도 허용한다.
       (예: 현장학습 결과 안내 → "박물관에서 뭐가 제일 재미있었어?" O)
     - 학부모가 이미 알고 있는 사실(자녀가 어디 갔는지, 무엇을 했는지 등)을
       단순히 확인하는 질문은 제외한다.
       (예: "오늘 현장학습 갔다 왔지?" X, "급식 먹었어?" X)
- 추출된 주제들은 반드시 서로 다른 관점에서 작성한다.
  아래 관점 중 서로 다른 3가지를 선택해 각 1개씩 작성한다:
  (1) 감정/기대: 자녀가 어떤 감정이나 기대를 가지고 있는지
      (예: "이번 현장학습에서 제일 기대되는 게 뭐야?")
  (2) 사회적 관계: 친구나 선생님과의 관계, 함께하는 활동
      (예: "어떤 친구랑 같이 다니고 싶어?")
  (3) 구체적 계획/준비: 당일 무엇을 할지, 뭘 가져갈지
      (예: "도시락 뭐 싸줄지 같이 골라볼까?")
  (4) 학습/경험: 새롭게 알게 될 것, 배울 내용
      (예: "거기서 어떤 걸 배울 수 있을 것 같아?")
  - 같은 관점에서 2개 이상 뽑지 않는다.
  - 위 4가지 관점 중 적합한 게 3개 미만이면 그 수만큼만 반환한다.
- 위 조건을 만족하는 주제가 없으면 빈 배열([])을 반환한다.
- topic은 학부모가 자녀에게 바로 말할 수 있는 자연스러운 구어체 문장으로 작성한다.
- topic은 항상 한국어로 작성한다. (사용자 언어로의 번역은 이후 단계에서 별도로 처리한다.)

한국어 작성 원칙 (title/summary/items[].title/checklistItems/conversationTopics):
{fact_basis_rule}
- translated_text는 참고하지 않는다. (단일 필드는 항상 한국어로 작성하므로 번역 초안이 필요 없다.)
- 학교명, 기관명, 행사명, 고유명사는 원문 표기를 그대로 사용한다.
- 날짜, 시간, 금액, 준비물, 제출 대상 같은 핵심 정보는 빠뜨리지 않는다.
- enum 값(type, dateStatus), datetime, timezone, selectedDateCandidate.originalText는
  schema와 원문 추적을 위해 그대로 둔다 (원래도 번역 대상 아님).
- evidenceText, confirmationQuestion도 한국어로 작성한다.

알림용 다국어 map 생성 원칙:
- titleI18n, items[].titleI18n, checklistItems[].contentI18n, checklistItems[].detailI18n은 반드시
  KO/US/ZH/VI 네 키를 모두 가진다.
- 이 map들은 알림 목록과 푸시 알림의 동적 값으로 쓰일 수 있으므로
  사용자의 현재 언어와 무관하게 네 언어를 모두 생성한다.
- items[].titleI18n은 캘린더 preview 일정 이름으로 바로 사용할 수 있는 짧은 이름이어야 한다.
- checklistItems[].contentI18n은 알림에 표시할 체크리스트/할 일 이름으로 바로 사용할 수 있어야 한다.
- conversationTopics는 알림에 쓰지 않으므로 다국어 map을 만들지 않는다.
- 네 언어 값 모두 original_text의 사실관계와 날짜, 금액, 준비물, 기관명, 행사명을 보존한다.
{document_section}
""".strip()


def _build_user_prompt(
    request: NewsletterAnalysisRequest,
    attached_documents: Sequence[AttachedDocument] = (),
) -> str:
    translated_text = request.translated_text.strip() if request.translated_text else ""
    reference_date = request.reference_date.isoformat() if request.reference_date else "null"
    language_name = _language_name(request.language)
    sections = [
        f"referenceDate: {reference_date}",
        f"timezone: {request.timezone}",
        f"language: {request.language}",
        f"targetLanguageName: {language_name}",
        "",
    ]
    if attached_documents:
        sections.extend(
            [
                "<attached_documents>",
                f"원본 문서 {len(attached_documents)}개가 이 메시지에 아래 순서대로 첨부되어 있다.",
                *(
                    f"{page}. {document.file_name} ({document.mime_type})"
                    for page, document in enumerate(attached_documents, start=1)
                ),
                "</attached_documents>",
                "",
            ]
        )
    sections.extend(
        [
            "<date_candidates>",
            _format_candidates(request),
            "</date_candidates>",
            "",
            "<original_text>",
            request.original_text.strip(),
            "</original_text>",
        ]
    )
    if translated_text:
        sections.extend(
            [
                "",
                "<translated_text>",
                "아래 translated_text는 기계 번역 초안입니다. title/summary/items[].title/",
                "checklistItems/conversationTopics(한국어 고정 필드)에는 사용하지 않는다.",
                "titleI18n/checklistItems[].contentI18n(알림용 다국어 map) 생성 시에만",
                "참고자료로 활용한다.",
                translated_text,
                "</translated_text>",
            ]
        )
    return "\n".join(sections)


def _language_name(language: str | None) -> str:
    normalized = (language or "KO").strip().upper()
    return LANGUAGE_NAMES.get(normalized, LANGUAGE_NAMES["KO"])


def _format_candidates(request: NewsletterAnalysisRequest) -> str:
    if not request.date_candidates:
        return "[]"

    lines = []
    for index, candidate in enumerate(request.date_candidates):
        span = source_span(request.original_text, candidate)
        context = request.original_text[max(0, span[0] - 100) : span[1] + 100] if span else None
        lines.append(
            f"- index: {index}, "
            f"candidateId: {candidate.candidate_id or 'null'}, "
            f"originalText: {candidate.original_text}, "
            f"normalizedDate: {candidate.normalized_date.isoformat()}, "
            f"startOffset: {candidate.start_offset}, "
            f"endOffset: {candidate.end_offset}, "
            f"extractionType: {candidate.extraction_type or 'null'}, "
            f"sourceContext: {json.dumps(context, ensure_ascii=False)}"
        )
    return "\n".join(lines)


REFINE_FIELD_SCHEMA = {
    "type": "string",
    "minLength": 1,
}

REFINE_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["fields"],
    "properties": {
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "text"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "text": REFINE_FIELD_SCHEMA,
                },
            },
        },
    },
}


def build_refine_prompt_messages(
    original_text: str,
    language: str,
    fields: list[dict[str, str]],
) -> list[dict[str, str]]:

    return [
        {"role": "system", "content": _build_refine_system_prompt(language)},
        {"role": "user", "content": _build_refine_user_prompt(original_text, fields)},
    ]


def _build_refine_system_prompt(language: str) -> str:
    language_name = _language_name(language)
    return f"""
역할: 가정통신문 원문(한국어)과, 그 일부 문구를 한국어 → {language_name}로
기계번역(파파고)한 결과 목록을 받아서 교정한다.

원칙:
- response schema에 맞는 JSON만 반환한다 (fields[] 배열).
- fields[]의 각 원소는 입력으로 받은 fields와 동일한 id를 가져야 하며,
  누락되거나 새로운 id를 추가하지 않는다. 입력 순서와 개수를 그대로 유지한다.
- 입력으로 받은 translatedText(파파고 번역 결과)를 기본 베이스로 삼는다.
- translatedText가 자연스럽고 원문(originalText, koText)의 의미와 일치하면
  그대로 text에 반환한다 (불필요한 재작성 금지).
- translatedText가 어색하거나, 원문 의미와 다르거나, 숫자/날짜/금액 등 핵심
  정보가 누락·왜곡된 경우에만 {language_name}로 자연스럽게 다듬어서 반환한다.
- 새로운 정보를 추가하거나 임의로 의역을 확장하지 않는다. 어디까지나 "교정"이지
  "재작성"이 아니다.
- text는 항상 {language_name}로 작성한다 (translatedText의 언어를 유지).
- 학교명, 기관명, 행사명, 고유명사도 모두 {language_name}로 번역한다.
  원문 한국어 표기를 그대로 남기지 않는다 (예: "서울노원초등학교"를 한국어
  그대로 두지 않고 {language_name} 표기/음역으로 변환한다).
""".strip()


def _build_refine_user_prompt(original_text: str, fields: list[dict[str, str]]) -> str:
    field_lines = []
    for field in fields:
        field_lines.append(
            f"- id: {field['id']}\n"
            f"  koText: {field['koText']}\n"
            f"  translatedText: {field['translatedText']}"
        )

    sections = [
        "<original_text>",
        original_text.strip(),
        "</original_text>",
        "",
        "<fields>",
        "\n".join(field_lines),
        "</fields>",
    ]
    return "\n".join(sections)
