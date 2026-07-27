import unittest

from app.schemas import ChatDocumentContext, ChatMessageItem, ChatRequest, ChatType
from app.services.chat_prompt import MAX_DOCUMENT_TEXT_LENGTH, build_chat_messages
from app.services.chat_service import ChatDocumentMissingError


def _document(
    original_text: str = "5월 22일 봄 현장학습을 갑니다.", **kwargs
) -> ChatDocumentContext:
    payload = {
        "newsletterId": 1,
        "title": "봄 현장학습 안내",
        "summary": "5월 22일 현장학습",
        "originalText": original_text,
    }
    payload.update(kwargs)
    return ChatDocumentContext.model_validate(payload)


class GeneralChatPromptTest(unittest.TestCase):
    """GENERAL 모드가 문서 챗봇 도입 이전과 동일하게 동작하는지 검증 (회귀 테스트)."""

    def test_general_메시지_구조는_시스템_히스토리_현재질문_순서다(self):
        request = ChatRequest(
            message="급식비는 얼마인가요?",
            history=[
                ChatMessageItem(role="user", content="안녕하세요"),
                ChatMessageItem(role="assistant", content="안녕하세요! 무엇을 도와드릴까요?"),
            ],
            language="KO",
            chatType="GENERAL",
        )
        messages = build_chat_messages(request)

        self.assertEqual([m["role"] for m in messages], ["system", "user", "assistant", "user"])
        self.assertEqual(messages[-1]["content"], "급식비는 얼마인가요?")

    def test_general은_문서_참고_메시지를_추가하지_않는다(self):
        request = ChatRequest(message="안녕", language="KO", chatType="GENERAL")
        messages = build_chat_messages(request)

        self.assertEqual(len(messages), 2)
        self.assertNotIn("본문:", "".join(m["content"] for m in messages))

    def test_general은_document가_있어도_무시한다(self):
        request = ChatRequest(
            message="안녕", language="KO", chatType="GENERAL", document=_document()
        )
        messages = build_chat_messages(request)

        self.assertEqual(len(messages), 2)
        self.assertNotIn("본문:", "".join(m["content"] for m in messages))

    def test_chat_type_기본값은_general이다(self):
        request = ChatRequest(message="안녕")
        self.assertEqual(request.chat_type, ChatType.GENERAL)

    def test_be가_보내는_camelCase_chatType이_반영된다(self):
        # 기존 버그: alias가 없어 chatType이 무시되고 항상 GENERAL로 처리되던 문제
        request = ChatRequest.model_validate(
            {
                "message": "안녕",
                "history": [],
                "language": "US",
                "chatType": "DOCUMENT",
                "document": {"originalText": "본문"},
            }
        )
        self.assertEqual(request.chat_type, ChatType.DOCUMENT)


class DocumentChatPromptTest(unittest.TestCase):
    """문서 챗봇(DOCUMENT) 프롬프트 구성 및 코드리뷰 반영 사항 검증."""

    def test_문서는_system이_아닌_별도_user_메시지로_전달된다(self):
        # 프롬프트 인젝션 방어: 외부 입력(OCR 본문)을 정적 지침과 분리
        request = ChatRequest(
            message="언제까지 내야 해요?", language="KO", chatType="DOCUMENT", document=_document()
        )
        messages = build_chat_messages(request)

        self.assertEqual([m["role"] for m in messages], ["system", "user", "user"])
        self.assertNotIn("5월 22일 봄 현장학습", messages[0]["content"])
        self.assertNotIn("본문:", messages[0]["content"])
        self.assertIn("<document>", messages[1]["content"])
        self.assertIn("5월 22일 봄 현장학습", messages[1]["content"])

    def test_프롬프트_인젝션_방어_지침이_system에_있다(self):
        request = ChatRequest(message="q", language="KO", chatType="DOCUMENT", document=_document())
        system_prompt = build_chat_messages(request)[0]["content"]

        self.assertIn("지시가 아닙니다", system_prompt)
        self.assertIn("이전 지시를 무시하라", system_prompt)

    def test_본문이_짧으면_절단_알림이_없다(self):
        request = ChatRequest(message="q", language="KO", chatType="DOCUMENT", document=_document())
        document_message = build_chat_messages(request)[1]["content"]

        self.assertNotIn("[알림]", document_message)

    def test_본문이_길면_잘리고_절단_알림이_붙는다(self):
        long_text = "가" * (MAX_DOCUMENT_TEXT_LENGTH + 500)
        request = ChatRequest(
            message="q", language="KO", chatType="DOCUMENT", document=_document(long_text)
        )
        document_message = build_chat_messages(request)[1]["content"]

        self.assertIn("[알림]", document_message)
        self.assertNotIn("가" * (MAX_DOCUMENT_TEXT_LENGTH + 1), document_message)

    def test_제목과_요약에도_길이_상한이_적용된다(self):
        request = ChatRequest(
            message="q",
            language="KO",
            chatType="DOCUMENT",
            document=_document(title="제" * 500, summary="요" * 3000),
        )
        document_message = build_chat_messages(request)[1]["content"]

        self.assertNotIn("제" * 201, document_message)
        self.assertNotIn("요" * 1001, document_message)


class DocumentValidationTest(unittest.TestCase):
    """originalText 누락이 422가 아니라 400 경로를 타는지 검증."""

    def test_originalText_키가_없어도_모델_생성에_성공한다(self):
        document = ChatDocumentContext.model_validate({"newsletterId": 1})
        self.assertIsNone(document.original_text)

    def test_문서_누락은_ChatDocumentMissingError로_이어진다(self):
        from app.services import chat_service

        for document in (
            None,
            ChatDocumentContext.model_validate({}),
            ChatDocumentContext.model_validate({"originalText": "   "}),
        ):
            request = ChatRequest(message="q", chatType="DOCUMENT", document=document)
            with self.assertRaises(ChatDocumentMissingError):
                chat_service.chat(request)


if __name__ == "__main__":
    unittest.main()
