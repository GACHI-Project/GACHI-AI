import json
import unittest
from datetime import date

from app.config import OpenAISettings
from app.schemas import NewsletterAnalysisRequest
from app.services import openai_adapter
from app.services.newsletter_document import (
    DocumentLoadError,
    LoadedDocument,
)
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
        self.assertNotIn("},{", retry_messages[-1]["content"])
        self.assertIn('"loc": "items.1"', retry_messages[-1]["content"])

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


class StubDocumentAdapter(StubOpenAINewsletterAdapter):
    """OpenAI 파일 업로드/삭제를 실제로 호출하지 않고 기록만 한다.

    upload_failures: 앞에서부터 이 횟수만큼 업로드를 실패시킨다. (-1이면 항상 실패)
    always_fail_file: 이 파일명은 항상 업로드를 실패시킨다.
    """

    def __init__(
        self,
        responses: list[dict],
        upload_failures: int = 0,
        always_fail_file: str | None = None,
    ) -> None:
        super().__init__(responses)
        self.upload_failures = upload_failures
        self.always_fail_file = always_fail_file
        self.upload_attempts: list[str] = []
        self.uploaded_ids: list[str] = []
        self.deleted_ids: list[str] = []

    def _post_multipart(self, path, *, fields, file_name, mime_type, content):
        self.upload_attempts.append(file_name)
        if (
            file_name == self.always_fail_file
            or self.upload_failures == -1
            or len(self.upload_attempts) <= self.upload_failures
        ):
            raise OpenAIAdapterError("업로드 실패")
        file_id = f"file-{len(self.uploaded_ids) + 1}"
        self.uploaded_ids.append(file_id)
        return {"id": file_id}

    def _delete_file(self, file_id: str) -> None:
        self.deleted_ids.append(file_id)


def _documents() -> list[LoadedDocument]:
    return [
        LoadedDocument("newsletter-page-1.pdf", "application/pdf", b"%PDF-1.4"),
        LoadedDocument("newsletter-page-2.png", "image/png", b"\x89PNG"),
    ]


def _request() -> NewsletterAnalysisRequest:
    return NewsletterAnalysisRequest(
        originalText="2026. 6. 15 수영 실기교육 안내",
        language="KO",
        referenceDate=date(2026, 6, 12),
    )


def _request_with_document_url() -> NewsletterAnalysisRequest:
    return NewsletterAnalysisRequest(
        originalText="2026. 6. 15 수영 실기교육 안내",
        language="KO",
        referenceDate=date(2026, 6, 12),
        documents=[
            {
                "fileUrl": "https://bucket.s3.amazonaws.com/a.pdf",
                "fileName": "newsletter-page-1.pdf",
                "mimeType": "application/pdf",
            }
        ],
    )


def _ok() -> dict:
    return {"output_text": json.dumps(_valid_response(), ensure_ascii=False)}


class OpenAIAdapterDocumentTest(unittest.TestCase):
    def test_attaches_documents_in_page_order_and_deletes_after_analysis(self):
        adapter = StubDocumentAdapter([_ok()])

        response = adapter.analyze(_request(), _documents())

        system_message, user_message = adapter.payloads[0]["input"]
        self.assertIn("원본 문서 사용 원칙", system_message["content"])
        content = user_message["content"]
        self.assertEqual(content[0]["type"], "input_text")
        self.assertIn("1. newsletter-page-1.pdf (application/pdf)", content[0]["text"])
        self.assertEqual(content[1],
                         {"type": "input_file", "file_id": "file-1", "detail": "high"})
        self.assertEqual(content[2],
                         {"type": "input_image", "file_id": "file-2", "detail": "high"})
        self.assertEqual(adapter.deleted_ids, ["file-1", "file-2"])
        self.assertEqual(response.meta["requestedDocumentCount"], 2)
        self.assertEqual(response.meta["attachedDocumentCount"], 2)

    def test_retries_upload_once_then_attaches(self):
        adapter = StubDocumentAdapter([_ok()], upload_failures=1)

        response = adapter.analyze(_request(), _documents()[:1])

        self.assertEqual(len(adapter.upload_attempts), 2)
        self.assertEqual(response.meta["attachedDocumentCount"], 1)

    def test_falls_back_to_text_only_when_upload_keeps_failing(self):
        adapter = StubDocumentAdapter([_ok()], upload_failures=-1)

        response = adapter.analyze(_request(), _documents())

        system_message, user_message = adapter.payloads[0]["input"]
        self.assertIsInstance(user_message["content"], str)
        self.assertNotIn("원본 문서 사용 원칙", system_message["content"])
        self.assertEqual(response.meta["requestedDocumentCount"], 2)
        self.assertEqual(response.meta["attachedDocumentCount"], 0)

    def test_deletes_already_uploaded_pages_when_later_page_fails(self):
        # 1페이지 업로드 성공 → 2페이지 2회 모두 실패 → 1페이지도 지우고 텍스트로 진행
        adapter = StubDocumentAdapter([_ok()], always_fail_file="newsletter-page-2.png")

        response = adapter.analyze(_request(), _documents())

        self.assertEqual(adapter.deleted_ids, ["file-1"])
        self.assertIsInstance(adapter.payloads[0]["input"][1]["content"], str)
        self.assertEqual(response.meta["attachedDocumentCount"], 0)

    def test_deletes_documents_even_when_analysis_fails(self):
        invalid = _valid_response()
        invalid["items"] = ["},{"]
        bad = {"output_text": json.dumps(invalid, ensure_ascii=False)}
        adapter = StubDocumentAdapter([bad, bad])

        with self.assertRaises(OpenAIAdapterError):
            adapter.analyze(_request(), _documents())

        self.assertEqual(adapter.deleted_ids, ["file-1", "file-2"])

    def test_downloads_request_documents_when_documents_are_not_given(self):
        adapter = StubDocumentAdapter([_ok()])
        request = _request_with_document_url()
        original = openai_adapter.load_documents
        openai_adapter.load_documents = lambda documents, **kwargs: _documents()[:1]
        try:
            response = adapter.analyze(request)
        finally:
            openai_adapter.load_documents = original

        self.assertEqual(response.meta["requestedDocumentCount"], 1)
        self.assertEqual(response.meta["attachedDocumentCount"], 1)

    def test_falls_back_to_text_only_when_download_fails(self):
        adapter = StubDocumentAdapter([_ok()])
        request = _request_with_document_url()

        def fail(documents, **kwargs):
            raise DocumentLoadError("다운로드 실패")

        original = openai_adapter.load_documents
        openai_adapter.load_documents = fail
        try:
            response = adapter.analyze(request)
        finally:
            openai_adapter.load_documents = original

        self.assertEqual(adapter.upload_attempts, [])
        self.assertIsInstance(adapter.payloads[0]["input"][1]["content"], str)
        self.assertEqual(response.meta["requestedDocumentCount"], 1)
        self.assertEqual(response.meta["attachedDocumentCount"], 0)

if __name__ == "__main__":
    unittest.main()
