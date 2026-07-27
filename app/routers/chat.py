from fastapi import APIRouter, HTTPException, status

from app.schemas import ChatRequest, ChatResponse
from app.services.chat_service import ChatDocumentMissingError, chat
from app.services.openai_adapter import OpenAIAdapterError, OpenAIConfigurationError

router = APIRouter(prefix="/ai/chat", tags=["chat"])


@router.post("/messages", response_model=ChatResponse)
def send_message(req: ChatRequest) -> ChatResponse:
    try:
        return chat(req)
    except ChatDocumentMissingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except OpenAIConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except OpenAIAdapterError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
