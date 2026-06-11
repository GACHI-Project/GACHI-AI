from app.constants import LANGUAGE_NAMES, SUPPORTED_LANGUAGE_CODES
from app.schemas import NewsletterAnalysisRequest

I18N_TEXT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": list(SUPPORTED_LANGUAGE_CODES),
    "properties": {
        code: {"type": "string", "minLength": 1, "maxLength": 500}
        for code in SUPPORTED_LANGUAGE_CODES
    },
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
    "required": ["content", "contentI18n", "detail"],
    "properties": {
        "content": {"type": "string", "minLength": 1, "maxLength": 500},
        "contentI18n": I18N_TEXT_SCHEMA,
        "detail": {"type": ["string", "null"], "maxLength": 500},
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
            "additionalProperties": True,
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


def build_prompt_messages(request: NewsletterAnalysisRequest) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _build_system_prompt(request.language)},
        {"role": "user", "content": _build_user_prompt(request)},
    ]


def _build_system_prompt(language: str) -> str:
    language_name = _language_name(language)
    return f"""
역할: 학교 가정통신문 원문을 분석해서 저장 가능한 제목, 요약,
주요 일정/마감/체크리스트 항목을 JSON으로 반환한다.

- response schema에 맞는 JSON만 반환한다.
- AI 서버는 DB 저장을 직접 알지 않는다. 저장 판단은 BE가 하며, AI 서버는 분석 결과만 반환한다.
- title, summary, items[].title, checklistItems[].content, checklistItems[].detail,
  conversationTopics[].topic은 사용자 언어({language_name})와 무관하게 항상 한국어로 작성한다.
  (이 값들은 이후 단계에서 번역 및 검수를 거쳐 사용자 언어로 변환된다.)
- 단, titleI18n과 checklistItems[].contentI18n은 기존과 동일하게 KO/US/ZH/VI
  네 언어 값을 모두 채운다. 이 값들은 사용자의 현재 언어({language_name})와
  무관하게 알림(notification)에서 사용된다.
- title은 문서 제목으로 사용할 수 있는 짧은 문자열로 작성한다.
- titleI18n은 알림에서 사용할 문서 제목이며 KO/US/ZH/VI 네 언어 값을 모두 채운다.
- summary는 보호자나 학생이 빠르게 확인할 수 있는 1~2문장으로 작성한다.
- items의 구조는 /ai/newsletters/extract-items 응답 형식을 유지한다.
- 구체적인 날짜는 제공된 dateCandidates 중 하나만 선택한다.
- dateCandidates에 없는 날짜를 새로 만들거나 추론해서 confirmed로 반환하지 않는다.
- 날짜 근거가 명확할 때만 dateStatus를 confirmed로 설정한다.
- 날짜 정보가 없거나 근거가 약하면 ambiguous 또는 missing을 사용한다.
- evidenceText는 사용자가 볼 수 있는 근거/상세 설명 문구로 작성하되, 원문 의미를 벗어나지 않는다.

항목 분류 기준 (items[] 최상위 — 모두 "일정"이다):
- deadline: 제출, 신청, 납부, 등록, 동의, 회신, 마감 행동
- schedule: 행사, 수업, 상담, 체험학습, 설명회, 운영일
- reminder: deadline이나 schedule은 아니지만 알림으로 보여줄 가치가 있는 항목

체크리스트(checklistItems) 추출 원칙:
- 체크리스트는 더 이상 독립적인 최상위 항목이 아니다. 반드시 items[] 중
  하나의 일정(schedule/deadline/reminder)에 속한 checklistItems[]로만 추출한다.
- 체크리스트는 그 일정의 날짜를 그대로 따라간다. checklistItems 각 원소에는
  날짜 관련 필드를 절대 포함하지 않는다 (content, detail만 작성).
- 모든 일정에 체크리스트가 있어야 하는 것은 아니다. 해당 일정과 관련해
  학부모나 자녀가 실제로 준비하거나 수행해야 할 행동이 명확할 때만 추출하고,
  없으면 checklistItems: [] (빈 배열)로 둔다.
- 문서 전체 맥락을 통합적으로 파악해서 작성한다. 같은 행동(예: "신청서 제출하기"와
  "참가 동의서 제출하기")을 여러 일정에 중복으로 나누어 넣지 않는다. 하나의 행동은
  그 행동과 가장 직접적으로 연관된 단 하나의 일정에만 귀속시킨다.
- 같은 일정 내에서도 checklistItems끼리 서로 중복되거나 사실상 같은 행동을
  표현하는 항목을 여러 개 만들지 않는다.
- content는 다문화 학부모가 실제로 수행할 수 있는 구체적 행동 단위로,
  "OO 제출하기", "OO 준비하기", "OO 동의서 작성하기"처럼 행동 지향적인
  짧은 문구로 작성하되, 항상 한국어로 작성한다. (사용자 언어로의 번역은
  이후 단계에서 별도로 처리한다.)
- contentI18n은 알림에서 사용할 체크리스트/할 일 이름이며 KO/US/ZH/VI 값을 모두 채운다.
- detail은 그 항목에 대한 부가 설명을 원문 근거에 기반해 1줄로 작성한다.
  (특별한 부가 설명이 없으면 null 가능)
- 체크리스트 문구는 BE에서 다시 번역하지 않고 바로 저장/표시할 수 있어야 한다.
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
- original_text는 사실 판단의 기준이다.
- translated_text는 참고하지 않는다. (단일 필드는 항상 한국어로 작성하므로 번역 초안이 필요 없다.)
- 학교명, 기관명, 행사명, 고유명사는 원문 표기를 그대로 사용한다.
- 날짜, 시간, 금액, 준비물, 제출 대상 같은 핵심 정보는 빠뜨리지 않는다.
- enum 값(type, dateStatus), datetime, timezone, selectedDateCandidate.originalText는
  schema와 원문 추적을 위해 그대로 둔다 (원래도 번역 대상 아님).
- evidenceText, confirmationQuestion도 한국어로 작성한다.

알림용 다국어 map 생성 원칙:
- titleI18n, items[].titleI18n, checklistItems[].contentI18n은 반드시
  KO/US/ZH/VI 네 키를 모두 가진다.
- 이 map들은 알림 목록과 푸시 알림의 동적 값으로 쓰일 수 있으므로
  사용자의 현재 언어와 무관하게 네 언어를 모두 생성한다.
- items[].titleI18n은 캘린더 preview 일정 이름으로 바로 사용할 수 있는 짧은 이름이어야 한다.
- checklistItems[].contentI18n은 알림에 표시할 체크리스트/할 일 이름으로 바로 사용할 수 있어야 한다.
- conversationTopics는 알림에 쓰지 않으므로 다국어 map을 만들지 않는다.
- 네 언어 값 모두 original_text의 사실관계와 날짜, 금액, 준비물, 기관명, 행사명을 보존한다.
""".strip()


def _build_user_prompt(request: NewsletterAnalysisRequest) -> str:
    translated_text = request.translated_text.strip() if request.translated_text else ""
    reference_date = request.reference_date.isoformat() if request.reference_date else "null"
    language_name = _language_name(request.language)
    sections = [
        f"referenceDate: {reference_date}",
        f"timezone: {request.timezone}",
        f"language: {request.language}",
        f"targetLanguageName: {language_name}",
        "",
        "<date_candidates>",
        _format_candidates(request),
        "</date_candidates>",
        "",
        "<original_text>",
        request.original_text.strip(),
        "</original_text>",
    ]
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
        lines.append(
            f"- index: {index}, "
            f"candidateId: {candidate.candidate_id or 'null'}, "
            f"originalText: {candidate.original_text}, "
            f"normalizedDate: {candidate.normalized_date.isoformat()}, "
            f"startOffset: {candidate.start_offset}, "
            f"endOffset: {candidate.end_offset}, "
            f"extractionType: {candidate.extraction_type or 'null'}"
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
