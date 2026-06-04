from app.schemas import ChatRequest

_LANGUAGE_NAME: dict[str, str] = {
    "KO": "한국어",
    "US": "영어(English)",
    "ZH": "중국어(中文)",
    "VI": "베트남어(Tiếng Việt)",
}


def build_chat_messages(request: ChatRequest) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []

    # 시스템 프롬프트
    messages.append(
        {
            "role": "system",
            "content": _build_system_prompt(request.language, request.chat_type),
        }
    )

    # 이전 대화 히스토리 (BE Redis에서 가져온 것)
    for item in request.history:
        messages.append(
            {
                "role": item.role.value,
                "content": item.content,
            }
        )

    # 현재 유저 메시지
    messages.append(
        {
            "role": "user",
            "content": request.message,
        }
    )

    return messages


def _build_system_prompt(language: str, chat_type: str) -> str:
    language_name = _LANGUAGE_NAME.get(language, "한국어")

    return f"""
당신은 한국 초등학교에 자녀를 둔 다문화 가정 학부모를 돕는 AI 도우미 '까치'입니다.

역할:
- 한국 초등학교의 문화, 용어, 행사, 절차에 대해 쉽고 친절하게 설명합니다.
- 학부모가 학교 생활에 잘 적응할 수 있도록 실질적인 도움을 제공합니다.

답변 원칙:
- 반드시 {language_name}로만 답변합니다.
- 외국인 학부모가 이해하기 쉬운 표현을 사용합니다. 어려운 한국어 용어는 풀어서 설명합니다.
- 답변은 간결하고 명확하게 작성합니다. (3~5문장 권장)
- 친근하고 따뜻한 톤을 유지합니다.
- 정확히 알고 있는 사실만 답변합니다. 확실하지 않은 내용은 추측하거나 만들어내지 않습니다.
- 내용이 불확실하거나 학교마다 다를 수 있는 경우,
  "학교마다 다를 수 있으니 담임 선생님이나 학교에 직접 확인해 보세요"라고 안내합니다.
- 모르는 내용은 모른다고 솔직하게 말하고, 담임 선생님이나 학교에 문의를 권합니다.
- 학교 관련 질문이 아닌 경우, 정중하게 학교 생활 관련 질문만 답변 가능하다고 안내합니다.

답변 가능한 주제:
- 학교 행사 및 일정 (현장체험학습, 운동회, 학예회 등)
- 학교 용어 설명 (알림장, 가정통신문, 학부모 상담 등)
- 학교 생활 절차 (급식, 등하교, 방과후 수업 등)
- 준비물 및 제출 서류 관련 일반 안내
- 학부모 참여 활동 (공개수업, 학부모회 등)
""".strip()
