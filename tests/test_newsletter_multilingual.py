import os
import unittest
from datetime import date

from app.constants import SUPPORTED_LANGUAGE_CODES
from app.schemas import NewsletterAnalysisRequest
from app.services.newsletter_extractor import analyze_newsletter
from app.services.newsletter_prompt import ANALYSIS_RESPONSE_SCHEMA, build_prompt_messages


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

        notification_us_phrase = (
            "사용자의 현재 언어(미국 영어)와\n  무관하게 알림(notification)에서 사용된다"
        )
        self.assertIn(notification_us_phrase, system_prompt)
        self.assertIn(
            "conversationTopics[].topic은 사용자 언어(미국 영어)와 무관하게 항상 한국어로 작성한다",
            system_prompt,
        )
        self.assertIn("체크리스트 문구는 BE에서 다시 번역하지 않고 바로 저장/표시", system_prompt)
        self.assertIn("topic은 항상 한국어로 작성한다", system_prompt)
        translated_text_skip_phrase = (
            "translated_text는 참고하지 않는다. "
            "(단일 필드는 항상 한국어로 작성하므로 번역 초안이 필요 없다.)"
        )
        self.assertIn(translated_text_skip_phrase, system_prompt)
        self.assertIn("targetLanguageName: 미국 영어", user_prompt)
        self.assertIn("아래 translated_text는 기계 번역 초안입니다.", user_prompt)
        self.assertIn("알림용 다국어 map 생성 원칙", system_prompt)
        self.assertIn(
            "conversationTopics는 알림에 쓰지 않으므로 다국어 map을 만들지 않는다", system_prompt
        )

    def test_analysis_schema_requires_notification_i18n_maps(self):
        response_properties = ANALYSIS_RESPONSE_SCHEMA["properties"]
        item_properties = response_properties["items"]["items"]["properties"]
        checklist_properties = item_properties["checklistItems"]["items"]["properties"]

        self.assertIn("titleI18n", ANALYSIS_RESPONSE_SCHEMA["required"])
        self.assertIn("titleI18n", item_properties)
        self.assertIn("contentI18n", checklist_properties)
        self.assertEqual(
            set(response_properties["titleI18n"]["required"]),
            set(SUPPORTED_LANGUAGE_CODES),
        )

    def test_prompt_falls_back_to_korean_for_unknown_language(self):
        request = NewsletterAnalysisRequest(
            originalText="가정통신문",
            language="UNKNOWN",
        )

        messages = build_prompt_messages(request)

        notification_i18n_phrase = (
            "사용자의 현재 언어(한국어)와\n  무관하게 알림(notification)에서 사용된다"
        )
        self.assertIn(notification_i18n_phrase, messages[0]["content"])
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
        self.assertEqual(set(response.title_i18n), set(SUPPORTED_LANGUAGE_CODES))
        self.assertEqual(
            response.title_i18n["US"],
            "Saturday Bakery Program Application Guide",
        )
        self.assertEqual(response.meta["outputLanguage"], "US")
        self.assertFalse(response.meta["localizedOutput"])
        self.assertTrue(response.meta["requiresLLMReview"])


if __name__ == "__main__":
    unittest.main()
