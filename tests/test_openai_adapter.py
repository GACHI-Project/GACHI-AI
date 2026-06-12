import json
import unittest
from datetime import date

from app.config import OpenAISettings
from app.schemas import NewsletterAnalysisRequest
from app.services.openai_adapter import OpenAIAdapterError, OpenAINewsletterAdapter


def _i18n(text: str) -> dict[str, str]:
    return {"KO": text, "US": text, "ZH": text, "VI": text}


def _valid_response() -> dict:
    return {
        "title": "수영 실기교육 안내",
        "titleI18n": _i18n("수영 실기교육 안내"),
        "summary": "수영 실기교육 일정을 확인하세요.",
        "items": [
            {
                "type": "schedule",
                "title": "수영 실기교육",
                "titleI18n": _i18n("수영 실기교육"),
                "selectedDateCandidate": {
                    "index": 0,
                    "candidateId": "dc_1",
                    "originalText": "2026. 6. 15",
                    "normalizedDate": "2026-06-15",
                },
                "dateStatus": "confirmed",
                "datetime": "2026-06-15",
                "timezone": "Asia/Seoul",
                "evidenceText": "2026. 6. 15 수영 실기교육",
                "confidence": 0.9,
                "needsUserConfirmation": False,
                "confirmationQuestion": None,
                "checklistItems": [
                    {
                        "content": "수영복 준비하기",
                        "contentI18n": _i18n("수영복 준비하기"),
                        "detail": "수영복, 수영모, 물안경을 준비합니다.",
                        "detailI18n": _i18n("수영복, 수영모, 물안경을 준비합니다."),
                    }
                ],
            }
        ],
        "conversationTopics": [],
        "meta": {
            "mode": "openai",
            "dateCandidateCount": 1,
            "requiresLLMReview": False,
            "outputLanguage": "KO",
            "localizedOutput": True,
        },
    }


class StubOpenAINewsletterAdapter(OpenAINewsletterAdapter):
    def __init__(self, responses: list[dict]) -> None:
        super().__init__(
            OpenAISettings(
                enabled=True,
                api_key="test-key",
                model="test-model",
                base_url="https://example.test/v1",
                timeout_seconds=1,
            )
        )
        self.responses = responses
        self.payloads: list[dict] = []

    def _post_json(self, path: str, payload: dict) -> dict:
        self.payloads.append(payload)
        index = len(self.payloads) - 1
        return self.responses[index]


class OpenAIAdapterSchemaRetryTest(unittest.TestCase):
    def test_analyze_retries_once_when_schema_validation_fails(self):
        invalid = _valid_response()
        invalid["items"] = [invalid["items"][0], "},{"]
        adapter = StubOpenAINewsletterAdapter(
            [
                {"output_text": json.dumps(invalid, ensure_ascii=False)},
                {"output_text": json.dumps(_valid_response(), ensure_ascii=False)},
            ]
        )
        request = NewsletterAnalysisRequest(
            originalText="2026. 6. 15 수영 실기교육 안내",
            language="KO",
            referenceDate=date(2026, 6, 12),
        )

        response = adapter.analyze(request)

        self.assertEqual(response.title, "수영 실기교육 안내")
        self.assertEqual(len(adapter.payloads), 2)
        retry_messages = adapter.payloads[1]["input"]
        self.assertIn("스키마 검증에 실패", retry_messages[-1]["content"])
        self.assertIn("items 배열의 모든 원소", retry_messages[-1]["content"])

    def test_analyze_raises_after_retry_also_fails_validation(self):
        invalid = _valid_response()
        invalid["items"] = [invalid["items"][0], "},{"]
        adapter = StubOpenAINewsletterAdapter(
            [
                {"output_text": json.dumps(invalid, ensure_ascii=False)},
                {"output_text": json.dumps(invalid, ensure_ascii=False)},
            ]
        )
        request = NewsletterAnalysisRequest(
            originalText="2026. 6. 15 수영 실기교육 안내",
            language="KO",
            referenceDate=date(2026, 6, 12),
        )

        with self.assertRaises(OpenAIAdapterError):
            adapter.analyze(request)
        self.assertEqual(len(adapter.payloads), 2)


if __name__ == "__main__":
    unittest.main()
