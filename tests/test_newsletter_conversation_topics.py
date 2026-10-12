from app.schemas import NewsletterAnalysisRequest
from app.services.newsletter_prompt import ANALYSIS_RESPONSE_SCHEMA, build_prompt_messages


def _system_prompt() -> str:
    request = NewsletterAnalysisRequest(originalText="가정통신문")
    content = build_prompt_messages(request)[0]["content"]
    return " ".join(content.split())


def test_conversation_topic_prompt_prioritizes_natural_and_useful_questions():
    prompt = _system_prompt()

    assert "실제로 바로 물어볼 만한" in prompt
    assert "개수를 채우기 위해 질문을 만들지 않는다" in prompt
    assert "기본값은 빈 배열([])" in prompt
    assert "질문을 위한 질문은 제외" in prompt
    assert "실제 대화에 도움이 될지 불분명하면 제외" in prompt


def test_conversation_topic_prompt_allows_no_recommendation_without_forcing_categories():
    prompt = _system_prompt()

    assert "반드시 빈 배열([])을 반환" in prompt
    assert "대화 주제를 미리 정한 유형에 맞추지 않는다" in prompt
    assert "(1) 감정/기대" not in prompt
    assert "서로 다른 3가지를 선택" not in prompt


def test_conversation_topic_prompt_keeps_grounding_and_tense_rules():
    prompt = _system_prompt()

    assert "문서에 없는 경험, 감정, 관계, 계획을 임의로 가정하지 않는다" in prompt
    assert "행정·보호자 대상 내용은 제외" in prompt
    assert "준비 서류, 절차인 질문" in prompt
    assert "보험 청구 등의 행정 업무" in prompt
    assert "질문의 답을 문서에서 찾아야 한다면 제외" in prompt
    assert "conversationTopics=[]로 고정" in prompt
    assert "행정 절차를 자녀 질문으로 바꾸는 것도 금지" in prompt
    assert "급식, 하교 시간, 비용, 제출물" in prompt
    assert "운영 정보에 '기대돼?'" in prompt
    assert '"개학식 날 급식이 나오는 거 기대돼?"' in prompt
    assert '"단축수업 날 일찍 끝나서 좋아?"' in prompt
    assert "운영 정보를 소재로 한 추가 질문은 모두 버린다" in prompt
    assert "기대·선호를 묻는 문장이어도 삭제" in prompt
    assert "학교안전공제회 청구 절차" in prompt
    assert 'conversationTopics=[{"topic":"운동회에서 어떤 경기가 가장 기대돼?"}]' in prompt
    assert '"운동회 날 점심에는 무슨 음식을 먹고 싶니?"' in prompt
    assert '"만약 학교에서 다치면 누구에게 알려야 할까?"' in prompt
    assert "자녀가 아닌 보호자가 답해야 하면 삭제" in prompt
    assert "신청/예정 안내" in prompt
    assert "결과/완료 안내" in prompt
    assert "단순히 확인하는 질문은 제외" in prompt


def test_conversation_topic_schema_allows_zero_to_three_topics():
    schema = ANALYSIS_RESPONSE_SCHEMA["properties"]["conversationTopics"]

    assert schema["minItems"] == 0
    assert schema["maxItems"] == 3
