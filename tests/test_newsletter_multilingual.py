import os
import unittest
from datetime import date

from app.schemas import NewsletterAnalysisRequest
from app.services.newsletter_extractor import analyze_newsletter
from app.services.newsletter_prompt import build_prompt_messages


class NewsletterMultilingualPromptTest(unittest.TestCase):
    def test_prompt_requires_final_user_text_in_target_language(self):
        request = NewsletterAnalysisRequest(
            originalText="토요 와글와글 베이커리 프로그램 신청 안내",
            translatedText="Saturday bakery program application guide",
            language="US",
            referenceDate=date(2026, 6, 11),
        )

        messages = build_prompt_messages(request)
        system_prompt = messages[0]["content"]
        user_prompt = messages[1]["content"]

        self.assertIn("최종 사용자 노출 문구는 반드시 미국 영어로 작성", system_prompt)
        self.assertIn("체크리스트 문구는 BE에서 다시 번역하지 않고 바로 저장/표시", system_prompt)
        self.assertIn("topic도 최종 사용자 노출 문구이므로 반드시 미국 영어로 작성", system_prompt)
        self.assertIn("translated_text가 있으면 초벌 번역/참고자료로만 사용", system_prompt)
        self.assertIn("targetLanguageName: 미국 영어", user_prompt)
        self.assertIn(
            "아래 translated_text는 기계 번역 초안이며 최종 문구가 아닙니다.", user_prompt
        )

    def test_prompt_falls_back_to_korean_for_unknown_language(self):
        request = NewsletterAnalysisRequest(
            originalText="가정통신문",
            language="UNKNOWN",
        )

        messages = build_prompt_messages(request)

        self.assertIn("최종 사용자 노출 문구는 반드시 한국어로 작성", messages[0]["content"])
        self.assertIn("targetLanguageName: 한국어", messages[1]["content"])


class NewsletterMultilingualFallbackTest(unittest.TestCase):
    def setUp(self):
        self.previous_openai_enabled = os.environ.get("OPENAI_ENABLED")
        os.environ["OPENAI_ENABLED"] = "false"

    def tearDown(self):
        if self.previous_openai_enabled is None:
            os.environ.pop("OPENAI_ENABLED", None)
        else:
            os.environ["OPENAI_ENABLED"] = self.previous_openai_enabled

    def test_rule_based_fallback_uses_translated_title_as_reference_for_non_korean(self):
        request = NewsletterAnalysisRequest(
            originalText="토요 와글와글 베이커리 프로그램 신청 안내\n6월 20일까지 신청하세요.",
            translatedText="Saturday Bakery Program Application Guide\nPlease apply by June 20.",
            language="US",
        )

        response = analyze_newsletter(request)

        self.assertEqual(response.title, "Saturday Bakery Program Application Guide")
        self.assertEqual(response.meta["outputLanguage"], "US")
        self.assertFalse(response.meta["localizedOutput"])
        self.assertTrue(response.meta["requiresLLMReview"])


if __name__ == "__main__":
    unittest.main()
