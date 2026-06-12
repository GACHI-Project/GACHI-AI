import json
import logging
import urllib.error
import urllib.request
from typing import Any

from pydantic import ValidationError

from app.config import OpenAISettings
from app.schemas import (
    NewsletterAnalysisRequest,
    NewsletterAnalysisResponse,
    TranslationRefineRequest,
    TranslationRefineResponse,
)
from app.services.newsletter_prompt import (
    ANALYSIS_RESPONSE_SCHEMA,
    REFINE_RESPONSE_SCHEMA,
    build_prompt_messages,
    build_refine_prompt_messages,
)

logger = logging.getLogger(__name__)

MAX_ANALYSIS_ATTEMPTS = 2


class OpenAIAdapterError(RuntimeError):
    pass


class OpenAIConfigurationError(OpenAIAdapterError):
    pass


class OpenAINewsletterAdapter:
    def __init__(self, settings: OpenAISettings) -> None:
        self.settings = settings

    def analyze(self, request: NewsletterAnalysisRequest) -> NewsletterAnalysisResponse:
        if not self.settings.api_key:
            raise OpenAIConfigurationError("OPENAI_API_KEY가 설정되어 있지 않습니다.")

        messages = build_prompt_messages(request)
        last_validation_error: ValidationError | None = None
        for attempt in range(1, MAX_ANALYSIS_ATTEMPTS + 1):
            response_body = self._post_json("/responses", self._analysis_payload(messages))
            parsed = self._extract_output_json(response_body)
            try:
                return NewsletterAnalysisResponse.model_validate(parsed)
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

    def _analysis_payload(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "model": self.settings.model,
            "input": messages,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "newsletter_analysis",
                    "schema": ANALYSIS_RESPONSE_SCHEMA,
                    "strict": False,
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
