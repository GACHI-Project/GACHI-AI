import json
import logging
import urllib.error
import urllib.request

from app.config import OpenAISettings, get_openai_settings
from app.schemas import ChatRequest, ChatResponse
from app.services.chat_prompt import build_chat_messages
from app.services.openai_adapter import OpenAIAdapterError, OpenAIConfigurationError

logger = logging.getLogger(__name__)


def chat(request: ChatRequest) -> ChatResponse:
    settings = get_openai_settings()

    if not settings.api_key:
        raise OpenAIConfigurationError("OPENAI_API_KEY가 설정되어 있지 않습니다.")

    messages = build_chat_messages(request)

    logger.info(
        "[ChatService] OpenAI 호출. language=%s, chat_type=%s, history_size=%d",
        request.language,
        request.chat_type,
        len(request.history),
    )

    reply = _call_openai_chat(settings, messages)

    logger.info("[ChatService] OpenAI 응답 수신 완료.")
    return ChatResponse(reply=reply)


def _call_openai_chat(settings: OpenAISettings, messages: list[dict[str, str]]) -> str:
    url = settings.base_url.rstrip("/") + "/chat/completions"

    payload = {
        "model": settings.model,
        "messages": messages,
        "max_tokens": 1000,
        "temperature": 0.7,
    }

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=settings.timeout_seconds) as response:
            response_body = json.loads(response.read().decode("utf-8"))

        reply = response_body["choices"][0]["message"]["content"]
        return reply.strip()

    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.warning(
            "[ChatService] OpenAI 호출 실패. status=%s, body_length=%s",
            exc.code,
            len(error_body),
        )
        raise OpenAIAdapterError(f"OpenAI 채팅 호출 실패. status={exc.code}") from exc

    except urllib.error.URLError as exc:
        logger.warning("[ChatService] OpenAI 통신 오류. reason=%s", exc.reason)
        raise OpenAIAdapterError("OpenAI 통신 오류가 발생했습니다.") from exc

    except TimeoutError as exc:
        logger.warning(
            "[ChatService] OpenAI 호출 timeout. timeout=%s",
            settings.timeout_seconds,
        )
        raise OpenAIAdapterError("OpenAI 호출 시간이 초과되었습니다.") from exc

    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        logger.warning("[ChatService] OpenAI 응답 파싱 실패. error=%s", exc)
        raise OpenAIAdapterError("OpenAI 채팅 응답을 파싱할 수 없습니다.") from exc
