from app.schemas import NewsletterAnalysisRequest

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

ITEM_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "type",
        "title",
        "selectedDateCandidate",
        "dateStatus",
        "datetime",
        "timezone",
        "evidenceText",
        "confidence",
        "needsUserConfirmation",
        "confirmationQuestion",
    ],
    "properties": {
        "type": {
            "type": "string",
            "enum": ["schedule", "deadline", "checklist", "reminder"],
        },
        "title": {"type": "string"},
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
    "required": ["title", "summary", "items", "conversationTopics", "meta"],
    "properties": {
        "title": {"type": "string"},
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
            },
        },
    },
}


def build_prompt_messages(request: NewsletterAnalysisRequest) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _build_system_prompt()},
        {"role": "user", "content": _build_user_prompt(request)},
    ]


def _build_system_prompt() -> str:
    return """
역할: 학교 가정통신문 원문을 분석해서 저장 가능한 제목, 요약,
주요 일정/마감/체크리스트 항목을 JSON으로 반환한다.

응답 원칙:
- response schema에 맞는 JSON만 반환한다.
- AI 서버는 DB 저장을 직접 알지 않는다. 저장 판단은 BE가 하며, AI 서버는 분석 결과만 반환한다.
- title은 문서 제목으로 사용할 수 있는 짧은 문자열로 작성한다.
- summary는 보호자나 학생이 빠르게 확인할 수 있는 1~2문장으로 작성한다.
- items의 구조는 /ai/newsletters/extract-items 응답 형식을 유지한다.
- 구체적인 날짜는 제공된 dateCandidates 중 하나만 선택한다.
- dateCandidates에 없는 날짜를 새로 만들거나 추론해서 confirmed로 반환하지 않는다.
- 날짜 근거가 명확할 때만 dateStatus를 confirmed로 설정한다.
- 날짜 정보가 없거나 근거가 약하면 ambiguous 또는 missing을 사용한다.
- evidenceText는 원문에서 직접 가져온 근거 문장이나 구절로 작성한다.

항목 분류 기준:
- deadline: 제출, 신청, 납부, 등록, 동의, 회신, 마감 행동
- schedule: 행사, 수업, 상담, 체험학습, 설명회, 운영일
- checklist: 준비물, 지참물, 확인 문서, 보호자나 학생이 해야 하는 행동
- reminder: deadline이나 schedule은 아니지만 알림으로 보여줄 가치가 있는 항목

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
- 주제는 한국어로만 작성한다. (번역은 BE에서 처리)
""".strip()


def _build_user_prompt(request: NewsletterAnalysisRequest) -> str:
    translated_text = request.translated_text.strip() if request.translated_text else ""
    reference_date = request.reference_date.isoformat() if request.reference_date else "null"
    sections = [
        f"referenceDate: {reference_date}",
        f"timezone: {request.timezone}",
        f"language: {request.language}",
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
        sections.extend(["", "<translated_text>", translated_text, "</translated_text>"])
    return "\n".join(sections)


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
