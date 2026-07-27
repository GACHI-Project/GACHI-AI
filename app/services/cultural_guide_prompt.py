from app.schemas import CulturalGuideRequest

# AI는 faqId만 고른다. 답변(answer) 본문은 절대 생성하지 않는다.
# (BE가 school_guide 테이블의 answer / answerI18n을 그대로 사용한다)
CULTURAL_GUIDE_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["selectedFaqs"],
    "properties": {
        "selectedFaqs": {
            "type": "array",
            "minItems": 0,
            "maxItems": 2,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["faqId", "relevanceReason"],
                "properties": {
                    "faqId": {"type": "integer", "minimum": 1},
                    "relevanceReason": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 200,
                    },
                },
            },
        },
    },
}

MAX_ORIGINAL_TEXT_LENGTH = 6000
MAX_TITLE_LENGTH = 200
MAX_SUMMARY_LENGTH = 1000
MAX_FAQ_CANDIDATE_COUNT = 300  # 현재 FAQ 180건. 증가 대비 여유값.
MAX_FAQ_QUESTION_LENGTH = 200
MAX_SELECTED_FAQ_COUNT = 2


def build_cultural_guide_prompt_messages(
    request: CulturalGuideRequest,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _build_system_prompt()},
        {"role": "user", "content": _build_user_prompt(request)},
    ]


def _build_system_prompt() -> str:
    return f"""
역할: 다문화 가정 학부모가 방금 스캔한 가정통신문 원문을 읽고,
미리 준비된 '학교 생활 가이드 FAQ' 후보 목록에서 이 문서와 직접 관련 있는 질문을 고른다.

이 기능의 목적:
- 한국 학교 문화에 익숙하지 않은 다문화 학부모가 이 가정통신문을 받았을 때
  "이건 왜 이렇게 하는 거지?", "이거 안 하면 어떻게 되지?" 하고 실제로 궁금해할 만한
  배경 설명을 미리 짚어주는 것이다.

출력 원칙:
- response schema에 맞는 JSON만 반환한다.
- faqCandidates에 실제로 존재하는 faqId만 사용한다. 새로운 id를 만들지 않는다.
- 최대 {MAX_SELECTED_FAQ_COUNT}개까지만 선택한다.
- 조건을 만족하는 FAQ가 하나도 없으면 반드시 빈 배열([])을 반환한다.
  억지로 개수를 채우지 않는다. 0개는 정상적인 결과다.
- 질문(question) 문구를 수정하거나 새로 쓰지 않는다. 선택만 한다.
- 답변(answer)은 절대 생성하지 않는다. 답변은 시스템이 DB에서 그대로 가져다 쓴다.

선택 기준 (아래를 모두 만족해야 선택한다):
1. 문서에서 실제로 다루는 상황과 직접 연결될 것.
   - 예: 동의서 제출을 요구하는 문서 → 동의서 제출 관련 FAQ (O)
   - 예: 급식 식단표 안내 문서 → 급식 알레르기/식단표 확인 FAQ (O)
2. 다문화 학부모가 이 문서를 받았을 때 실제로 궁금해할 내용일 것.
   - 한국인 학부모에게는 당연하지만 외국 배경 학부모에게는 낯선 절차·관행을 우선한다.
3. 단순히 같은 단어가 겹친다는 이유로 선택하지 않는다.
   - 예: 문서에 '학교'라는 단어가 있다고 해서 '학교'가 들어간 아무 FAQ나 고르지 않는다.
   - 예: 문서에 '신청'이 있다고 해서 관련 없는 '방과후학교 신청' FAQ를 고르지 않는다.
4. {MAX_SELECTED_FAQ_COUNT}개를 선택할 경우, 서로 다른 관점이나 서로 다른 category를 우선한다.
   - 같은 내용을 반복하는 두 FAQ를 함께 고르지 않는다.
5. 확신이 서지 않으면 선택하지 않는다.
   - 애매한 것을 2개 고르는 것보다, 확실한 것 1개만 고르거나 0개를 반환하는 것이 낫다.

relevanceReason 작성 원칙:
- 이 문서의 어떤 내용 때문에 해당 FAQ를 골랐는지 한국어 한 문장으로 짧게 적는다.
- 사용자 화면에는 노출되지 않는 내부 확인용 값이다.
""".strip()


def _build_user_prompt(request: CulturalGuideRequest) -> str:
    title = (request.title or "").strip()[:MAX_TITLE_LENGTH] or "(없음)"
    summary = (request.summary or "").strip()[:MAX_SUMMARY_LENGTH] or "(없음)"

    original_text = (request.original_text or "").strip()
    truncated = len(original_text) > MAX_ORIGINAL_TEXT_LENGTH
    if truncated:
        original_text = original_text[:MAX_ORIGINAL_TEXT_LENGTH]

    sections = [
        "<newsletter>",
        f"제목: {title}",
        f"요약: {summary}",
    ]
    if truncated:
        sections.append(f"[알림] 본문이 길어 앞부분 {MAX_ORIGINAL_TEXT_LENGTH}자만 전달되었습니다.")
    sections.extend(
        [
            "본문:",
            original_text,
            "</newsletter>",
            "",
            "<faq_candidates>",
            _format_faq_candidates(request),
            "</faq_candidates>",
        ]
    )
    return "\n".join(sections)


def _format_faq_candidates(request: CulturalGuideRequest) -> str:
    if not request.faq_candidates:
        return "(후보 없음)"

    lines = []
    for candidate in request.faq_candidates[:MAX_FAQ_CANDIDATE_COUNT]:
        question = (candidate.question or "").strip()[:MAX_FAQ_QUESTION_LENGTH]
        lines.append(
            f"- faqId: {candidate.faq_id}, category: {candidate.category}, question: {question}"
        )
    return "\n".join(lines)
