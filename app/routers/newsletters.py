from fastapi import APIRouter

from app.schemas import (
    NewsletterAnalysisRequest,
    NewsletterAnalysisResponse,
    NewsletterExtractionRequest,
    NewsletterExtractionResponse,
    PromptPreviewResponse,
)
from app.services.newsletter_extractor import analyze_newsletter, extract_newsletter_items
from app.services.newsletter_prompt import ANALYSIS_RESPONSE_SCHEMA, build_prompt_messages

router = APIRouter(prefix="/ai/newsletters", tags=["newsletters"])


@router.post("/analyze", response_model=NewsletterAnalysisResponse)
def analyze(req: NewsletterAnalysisRequest) -> NewsletterAnalysisResponse:
    return analyze_newsletter(req)


@router.post("/extract-items", response_model=NewsletterExtractionResponse)
def extract_items(req: NewsletterExtractionRequest) -> NewsletterExtractionResponse:
    return extract_newsletter_items(req)


@router.post("/prompt-preview", response_model=PromptPreviewResponse)
def prompt_preview(req: NewsletterExtractionRequest) -> PromptPreviewResponse:
    messages = build_prompt_messages(req)
    return PromptPreviewResponse(messages=messages, responseSchema=ANALYSIS_RESPONSE_SCHEMA)
