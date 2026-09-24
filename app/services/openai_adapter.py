import json
import logging
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.config import OpenAISettings
from app.schemas import (
    CulturalGuideRequest,
    CulturalGuideResponse,
    NewsletterAnalysisRequest,
    NewsletterAnalysisResponse,
    TranslationRefineRequest,
    TranslationRefineResponse,
)
from app.services.cultural_guide_prompt import (
    CULTURAL_GUIDE_RESPONSE_SCHEMA,
    build_cultural_guide_prompt_messages,
)
from app.services.newsletter_document import (
    DocumentLoadError,
    LoadedDocument,
    load_documents,
)
from app.services.newsletter_prompt import (
    ANALYSIS_RESPONSE_SCHEMA,
    REFINE_RESPONSE_SCHEMA,
    build_prompt_messages,
    build_refine_prompt_messages,
)
from app.services.newsletter_validation import normalize_analysis_dates

logger = logging.getLogger(__name__)

MAX_ANALYSIS_ATTEMPTS = 2
# 원본 문서 업로드 설정 추가
# 일시적 오류(네트워크, OpenAI 일시 장애)는 한 번만 다시 시도
MAX_FILE_UPLOAD_ATTEMPTS = 2
# user_data: PDF/이미지 모두 모델 입력용으로 쓸 수 있는 범용 purpose
FILE_PURPOSE = "user_data"
PDF_MIME_TYPE = "application/pdf"


class OpenAIAdapterError(RuntimeError):
    pass


class OpenAIConfigurationError(OpenAIAdapterError):
    pass


@dataclass(frozen=True)
class UploadedDocument:
    file_id: str
    file_name: str
    mime_type: str


class OpenAINewsletterAdapter:
    def __init__(self, settings: OpenAISettings) -> None:
        self.settings = settings

    # [원본 문서 첨부 흐름 추가 - analyze 메서드 전체 + 아래 보조 메서드들이 이 블록에 포함]
    # - 기존 분석 루프(스키마 오류 재시도)는 로직 그대로, finally로 파일을 지우기 위해
    #   try 블록 안으로 들여쓰기만 한 단계 들어갔다.
    # 1) 원본 문서 준비: documents를 직접 받으면 그대로 쓰고(평가 스크립트/테스트),
    #    없으면 요청의 Presigned URL에서 내려받는다.
    # 2) OpenAI Files API 업로드 → file_id로 분석 → finally에서 파일 삭제
    # 3) 다운로드/업로드가 (1회 재시도 후에도) 실패하면 원본 없이 기존 텍스트 분석으로 계속한다.
    #    이때 프롬프트와 날짜 검증도 기존 규칙 그대로 적용된다.
    def analyze(
        self,
        request: NewsletterAnalysisRequest,
        documents: list[LoadedDocument] | None = None,
    ) -> NewsletterAnalysisResponse:
        if not self.settings.api_key:
            raise OpenAIConfigurationError("OPENAI_API_KEY가 설정되어 있지 않습니다.")

        # 첨부를 시도한 문서 수. 첨부 실패(텍스트로 계속)한 경우를 meta에서 찾기 위해 남긴다.
        requested_document_count = (
            len(documents) if documents is not None else len(request.documents)
        )
        loaded_documents = self._prepare_documents(request, documents)
        uploaded_documents = self._upload_documents(loaded_documents)
        try:
            messages = self._attach_document_parts(
                build_prompt_messages(request, attached_documents=uploaded_documents),
                uploaded_documents,
            )
            # 여기부터 분석 루프. 스키마 오류 재시도 때도 같은 file_id를 그대로 쓴다.
            last_validation_error: ValidationError | None = None
            for attempt in range(1, MAX_ANALYSIS_ATTEMPTS + 1):
                response_body = self._post_json("/responses", self._analysis_payload(messages))
                # 토큰 사용량 로그
                self._log_usage(response_body, attempt, len(uploaded_documents))
                parsed = self._extract_output_json(response_body)
                try:
                    # 원본 첨부 여부를 날짜 검증과 meta에 전달
                    normalized = normalize_analysis_dates(
                        request,
                        NewsletterAnalysisResponse.model_validate(parsed),
                        documents_attached=bool(uploaded_documents),
                    )
                    return self._with_document_meta(
                        normalized,
                        requested_count=requested_document_count,
                        attached_count=len(uploaded_documents),
                    )
                except ValidationError as exc:
                    last_validation_error = exc
                    logger.warning(
                        "[OpenAIAdapter] 응답 스키마 검증 실패. attempt=%s/%s, errors=%s",
                        attempt,
                        MAX_ANALYSIS_ATTEMPTS,
                        self._summarize_validation_errors(exc, include_message=False),
                    )
                    if attempt < MAX_ANALYSIS_ATTEMPTS:
                        messages = [
                            *messages,
                            {
                                "role": "user",
                                "content": self._build_schema_retry_message(exc),
                            },
                        ]

            raise OpenAIAdapterError("OpenAI 응답이 분석 스키마와 일치하지 않습니다.") from (
                last_validation_error
            )
        # 분석 성공/실패와 관계없이 OpenAI에 올린 원본 문서를 삭제
        finally:
            self._delete_uploaded_documents(uploaded_documents)

    def _prepare_documents(
        self,
        request: NewsletterAnalysisRequest,
        documents: list[LoadedDocument] | None,
    ) -> list[LoadedDocument]:
        if documents is not None:
            return documents
        if not request.documents:
            return []
        try:
            return load_documents(
                request.documents,
                max_total_bytes=self.settings.document_max_bytes,
                timeout_seconds=self.settings.document_download_timeout_seconds,
            )
        except DocumentLoadError as exc:
            logger.warning(
                "[OpenAIAdapter] 원본 문서 준비 실패. 원본 없이 텍스트만으로 분석합니다. "
                "requestedDocumentCount=%s, reason=%s",
                len(request.documents),
                exc,
            )
            return []

    def _upload_documents(self, documents: list[LoadedDocument]) -> list[UploadedDocument]:
        """전부 올리거나 하나도 안 올린다. 일부만 올라가면 페이지가 빠진 원본이 되기 때문이다."""
        uploaded: list[UploadedDocument] = []
        if not documents:
            return uploaded
        try:
            for document in documents:
                uploaded.append(
                    UploadedDocument(
                        file_id=self._upload_file_with_retry(document),
                        file_name=document.file_name,
                        mime_type=document.mime_type,
                    )
                )
        except OpenAIAdapterError as exc:
            logger.warning(
                "[OpenAIAdapter] 원본 문서 업로드 실패. 원본 없이 텍스트만으로 분석합니다. "
                "documentCount=%s, uploadedBeforeFailure=%s, reason=%s",
                len(documents),
                len(uploaded),
                exc,
            )
            self._delete_uploaded_documents(uploaded)
            return []

        logger.info(
            "[OpenAIAdapter] 원본 문서 첨부 완료. documentCount=%s, mimeTypes=%s, detail=%s",
            len(uploaded),
            [document.mime_type for document in uploaded],
            self.settings.document_detail,
        )
        return uploaded

    def _upload_file_with_retry(self, document: LoadedDocument) -> str:
        for attempt in range(1, MAX_FILE_UPLOAD_ATTEMPTS + 1):
            try:
                return self._upload_file(document)
            except OpenAIAdapterError as exc:
                if attempt == MAX_FILE_UPLOAD_ATTEMPTS:
                    raise
                logger.warning(
                    "[OpenAIAdapter] 원본 문서 업로드 재시도. fileName=%s, attempt=%s/%s, "
                    "reason=%s",
                    document.file_name,
                    attempt,
                    MAX_FILE_UPLOAD_ATTEMPTS,
                    exc,
                )
        # for문 안에서 반드시 return 또는 raise 된다.
        raise OpenAIAdapterError("원본 문서 업로드에 실패했습니다.")

    def _upload_file(self, document: LoadedDocument) -> str:
        response_body = self._post_multipart(
            "/files",
            fields={
                "purpose": FILE_PURPOSE,
                # 삭제 요청이 실패해도 OpenAI에서 자동으로 지워지도록 만료 시간을 함께 건다.
                "expires_after[anchor]": "created_at",
                "expires_after[seconds]": str(self.settings.document_file_ttl_seconds),
            },
            file_name=document.file_name,
            mime_type=document.mime_type,
            content=document.content,
        )
        file_id = response_body.get("id")
        if not isinstance(file_id, str) or not file_id:
            raise OpenAIAdapterError("OpenAI 파일 업로드 응답에 file id가 없습니다.")
        return file_id

    def _delete_uploaded_documents(self, documents: list[UploadedDocument]) -> None:
        for document in documents:
            try:
                self._delete_file(document.file_id)
            except OpenAIAdapterError as exc:
                # 삭제 실패는 분석 결과에 영향을 주지 않는다. expires_after로 자동 삭제된다.
                logger.warning(
                    "[OpenAIAdapter] 원본 문서 삭제 실패. 만료 시간 후 자동 삭제됩니다. "
                    "fileId=%s, reason=%s",
                    document.file_id,
                    exc,
                )

    def _attach_document_parts(
        self, messages: list[dict[str, str]], documents: list[UploadedDocument]
    ) -> list[dict[str, Any]]:
        """user 메시지의 텍스트 뒤에 원본 문서를 페이지 순서대로 붙인다."""
        if not documents:
            return messages

        detail = self.settings.document_detail
        document_parts = [
            (
                {"type": "input_file", "file_id": document.file_id, "detail": detail}
                if document.mime_type == PDF_MIME_TYPE
                else {"type": "input_image", "file_id": document.file_id, "detail": detail}
            )
            for document in documents
        ]
        attached: list[dict[str, Any]] = []
        for message in messages:
            if message["role"] == "user":
                attached.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": message["content"]},
                            *document_parts,
                        ],
                    }
                )
            else:
                attached.append(message)
        return attached

    def _log_usage(self, response_body: dict[str, Any], attempt: int, document_count: int) -> None:
        usage = response_body.get("usage")
        if not isinstance(usage, dict):
            return
        logger.info(
            "[OpenAIAdapter] 분석 토큰 사용량. attempt=%s, documentCount=%s, detail=%s, "
            "inputTokens=%s, outputTokens=%s, totalTokens=%s",
            attempt,
            document_count,
            self.settings.document_detail if document_count else None,
            usage.get("input_tokens"),
            usage.get("output_tokens"),
            usage.get("total_tokens"),
        )

    def _with_document_meta(
        self,
        response: NewsletterAnalysisResponse,
        *,
        requested_count: int,
        attached_count: int,
    ) -> NewsletterAnalysisResponse:
        """원본을 요청받았지만 첨부하지 못한 경우를 평가/로그에서 찾을 수 있게 meta에 남긴다."""
        meta = dict(response.meta)
        meta["requestedDocumentCount"] = requested_count
        meta["attachedDocumentCount"] = attached_count
        return response.model_copy(update={"meta": meta})

    # [messages 타입 변경: user content가 원본 문서 배열이 될 수 있어 dict[str, Any]로 바뀜]
    def _analysis_payload(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "model": self.settings.model,
            "input": messages,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "newsletter_analysis",
                    "schema": ANALYSIS_RESPONSE_SCHEMA,
                    "strict": True,
                }
            },
        }

    def _build_schema_retry_message(self, exc: ValidationError) -> str:
        summarized_errors = self._summarize_validation_errors(exc, include_message=True)
        return (
            "이전 응답은 NewsletterAnalysisResponse 스키마 검증에 실패했습니다.\n"
            "아래 오류를 반드시 수정해 같은 schema의 JSON object만 다시 반환하세요.\n"
            "- items 배열의 모든 원소는 문자열이 아니라 JSON object여야 합니다.\n"
            "- checklistItems 배열의 모든 원소도 JSON object여야 합니다.\n"
            "- 누락된 required 필드가 있으면 schema에 맞게 모두 채우세요.\n"
            f"\nvalidationErrors:\n{json.dumps(summarized_errors, ensure_ascii=False)}"
        )

    def _summarize_validation_errors(
        self, exc: ValidationError, *, include_message: bool
    ) -> list[dict[str, str | None]]:
        summarized_errors = []
        for err in exc.errors()[:10]:
            summary = {
                "loc": ".".join(str(part) for part in err.get("loc", ())),
                "type": err.get("type"),
            }
            if include_message:
                summary["msg"] = err.get("msg")
            summarized_errors.append(summary)
        return summarized_errors

    def refine_translation(self, request: TranslationRefineRequest) -> TranslationRefineResponse:
        if not self.settings.api_key:
            raise OpenAIConfigurationError("OPENAI_API_KEY가 설정되어 있지 않습니다.")

        if not request.fields:
            return TranslationRefineResponse(fields=[])

        payload = {
            "model": self.settings.model,
            "input": build_refine_prompt_messages(
                request.original_text,
                request.language,
                [
                    {
                        "id": field.id,
                        "koText": field.ko_text,
                        "translatedText": field.translated_text,
                    }
                    for field in request.fields
                ],
            ),
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "translation_refine",
                    "schema": REFINE_RESPONSE_SCHEMA,
                    "strict": False,
                }
            },
        }

        response_body = self._post_json("/responses", payload)
        parsed = self._extract_output_json(response_body)
        try:
            return TranslationRefineResponse.model_validate(parsed)
        except ValidationError as exc:
            logger.warning("[OpenAIAdapter] 2차 검증 응답 스키마 검증 실패. error=%s", exc)
            raise OpenAIAdapterError("OpenAI 응답이 검증 스키마와 일치하지 않습니다.") from exc

    def select_cultural_guides(self, request: CulturalGuideRequest) -> CulturalGuideResponse:
        if not self.settings.api_key:
            raise OpenAIConfigurationError("OPENAI_API_KEY가 설정되어 있지 않습니다.")

        if not request.faq_candidates:
            return CulturalGuideResponse(selectedFaqs=[])

        payload = {
            "model": self.settings.model,
            "input": build_cultural_guide_prompt_messages(request),
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "cultural_guide_selection",
                    "schema": CULTURAL_GUIDE_RESPONSE_SCHEMA,
                    "strict": False,
                }
            },
        }

        response_body = self._post_json("/responses", payload)
        parsed = self._extract_output_json(response_body)
        try:
            return CulturalGuideResponse.model_validate(parsed)
        except ValidationError as exc:
            logger.warning("[OpenAIAdapter] 문화 맥락 응답 스키마 검증 실패. error=%s", exc)
            raise OpenAIAdapterError("OpenAI 응답이 문화 맥락 스키마와 일치하지 않습니다.") from exc

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = self.settings.base_url.rstrip("/") + path
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
            },
        )
        # [요청 전송/오류 처리를 _send_request로 분리]
        # (파일 업로드·삭제에서도 같은 오류 처리를 쓰기 위함)
        return self._send_request(req)

    def _post_multipart(
        self,
        path: str,
        *,
        fields: dict[str, str],
        file_name: str,
        mime_type: str,
        content: bytes,
    ) -> dict[str, Any]:
        """OpenAI Files API 업로드용 multipart/form-data 요청 (외부 라이브러리 없이 urllib 사용)."""
        boundary = f"----GachiBoundary{uuid.uuid4().hex}"
        body = bytearray()
        for name, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
            body.extend(f"{value}\r\n".encode())
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'.encode()
        )
        body.extend(f"Content-Type: {mime_type}\r\n\r\n".encode())
        body.extend(content)
        body.extend(f"\r\n--{boundary}--\r\n".encode())

        req = urllib.request.Request(
            self.settings.base_url.rstrip("/") + path,
            data=bytes(body),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        return self._send_request(req)

    def _delete_file(self, file_id: str) -> None:
        req = urllib.request.Request(
            self.settings.base_url.rstrip("/") + f"/files/{file_id}",
            method="DELETE",
            headers={"Authorization": f"Bearer {self.settings.api_key}"},
        )
        self._send_request(req)

    def _send_request(self, req: urllib.request.Request) -> dict[str, Any]:

        try:
            with urllib.request.urlopen(req, timeout=self.settings.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            logger.warning(
                "[OpenAIAdapter] OpenAI 호출 실패. status=%s, body_length=%s",
                exc.code,
                len(error_body),
            )
            raise OpenAIAdapterError(f"OpenAI 호출 실패. status={exc.code}") from exc
        except urllib.error.URLError as exc:
            logger.warning("[OpenAIAdapter] OpenAI 통신 오류. reason=%s", exc.reason)
            raise OpenAIAdapterError("OpenAI 통신 오류가 발생했습니다.") from exc
        except TimeoutError as exc:
            logger.warning(
                "[OpenAIAdapter] OpenAI 호출 timeout. timeout=%s",
                self.settings.timeout_seconds,
            )
            raise OpenAIAdapterError("OpenAI 호출 시간이 초과되었습니다.") from exc
        except json.JSONDecodeError as exc:
            logger.warning("[OpenAIAdapter] OpenAI 응답 JSON 파싱 실패. error=%s", exc)
            raise OpenAIAdapterError("OpenAI 응답을 JSON으로 해석할 수 없습니다.") from exc

    def _extract_output_json(self, response_body: dict[str, Any]) -> dict[str, Any]:
        output_text = response_body.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return self._loads_model_json(output_text)

        outputs = response_body.get("output", [])
        if not isinstance(outputs, list):
            raise OpenAIAdapterError("OpenAI 응답의 output 형식이 올바르지 않습니다.")

        for output in outputs:
            if not isinstance(output, dict):
                continue
            contents = output.get("content", [])
            if not isinstance(contents, list):
                continue
            for content in contents:
                if not isinstance(content, dict):
                    continue
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    return self._loads_model_json(text)

        raise OpenAIAdapterError("OpenAI 응답에서 출력 텍스트를 찾을 수 없습니다.")

    def _loads_model_json(self, value: str) -> dict[str, Any]:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            logger.warning(
                "[OpenAIAdapter] 모델 출력 JSON 파싱 실패. output_length=%s",
                len(value),
            )
            raise OpenAIAdapterError("OpenAI 모델 출력이 JSON 형식이 아닙니다.") from exc

        if not isinstance(parsed, dict):
            raise OpenAIAdapterError("OpenAI 모델 출력이 JSON object가 아닙니다.")
        return parsed
