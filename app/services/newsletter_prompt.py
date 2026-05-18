from app.schemas import NewsletterExtractionRequest

EXTRACTION_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
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
                    "selectedDateCandidate": {"type": ["object", "null"]},
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
            },
        }
    },
}


def build_prompt_messages(request: NewsletterExtractionRequest) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _build_system_prompt()},
        {"role": "user", "content": _build_user_prompt(request)},
    ]


def _build_system_prompt() -> str:
    return """
역할: 학교 가정통신문에서 캘린더, 알림, 체크리스트로 만들 항목을 추출한다.

핵심 규칙:
- 구체적인 날짜는 반드시 제공된 date candidates 중 하나만 선택할 것.
- date candidates에 없는 날짜를 새로 만들거나 추론하지 말 것.
- 날짜 근거가 명확할 때만 dateStatus를 "confirmed"로 설정할 것.
- 날짜 후보가 없거나 근거가 약하면 "ambiguous" 또는 "missing"을 사용할 것.
- evidenceText는 원문에서 짧게 가져올 것.
- response schema에 맞는 JSON만 반환할 것.

항목 분류 기준:
- deadline: 제출, 신청, 납부, 등록, 동의, 회신, 마감 행동
- schedule: 행사, 수업, 상담, 체험학습, 설명회, 운영일
- checklist: 준비물, 지참물, 확인 문서, 보호자나 학생이 해야 할 행동
- reminder: deadline이나 schedule은 아니지만 알림으로 보여줄 가치가 있는 항목
""".strip()


def _build_user_prompt(request: NewsletterExtractionRequest) -> str:
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


def _format_candidates(request: NewsletterExtractionRequest) -> str:
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
            f"endOffset: {candidate.end_offset}"
        )
    return "\n".join(lines)
