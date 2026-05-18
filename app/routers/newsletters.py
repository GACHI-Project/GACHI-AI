from fastapi import APIRouter

from app.schemas import (
    NewsletterExtractionRequest,
    NewsletterExtractionResponse,
    PromptPreviewResponse,
)
from app.services.newsletter_extractor import extract_newsletter_items
from app.services.newsletter_prompt import EXTRACTION_RESPONSE_SCHEMA, build_prompt_messages

router = APIRouter(prefix="/ai/newsletters", tags=["newsletters"])


@router.post("/extract-items", response_model=NewsletterExtractionResponse)
def extract_items(req: NewsletterExtractionRequest) -> NewsletterExtractionResponse:
    return extract_newsletter_items(req)


@router.post("/prompt-preview", response_model=PromptPreviewResponse)
def prompt_preview(req: NewsletterExtractionRequest) -> PromptPreviewResponse:
    messages = build_prompt_messages(req)
    return PromptPreviewResponse(messages=messages, responseSchema=EXTRACTION_RESPONSE_SCHEMA)
