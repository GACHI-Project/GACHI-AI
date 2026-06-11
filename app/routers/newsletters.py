from fastapi import APIRouter, HTTPException, status

from app.schemas import (
    NewsletterAnalysisRequest,
    NewsletterAnalysisResponse,
    NewsletterExtractionRequest,
    NewsletterExtractionResponse,
    PromptPreviewResponse,
    TranslationRefineRequest,
    TranslationRefineResponse,
)
from app.services.newsletter_extractor import (analyze_newsletter, extract_newsletter_items, refine_translation,)
from app.services.newsletter_prompt import ANALYSIS_RESPONSE_SCHEMA, build_prompt_messages
from app.services.openai_adapter import OpenAIAdapterError, OpenAIConfigurationError

router = APIRouter(prefix="/ai/newsletters", tags=["newsletters"])


@router.post("/analyze", response_model=NewsletterAnalysisResponse)
def analyze(req: NewsletterAnalysisRequest) -> NewsletterAnalysisResponse:
    try:
        return analyze_newsletter(req)
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


@router.post("/extract-items", response_model=NewsletterExtractionResponse)
def extract_items(req: NewsletterExtractionRequest) -> NewsletterExtractionResponse:
    return extract_newsletter_items(req)


@router.post("/prompt-preview", response_model=PromptPreviewResponse)
def prompt_preview(req: NewsletterExtractionRequest) -> PromptPreviewResponse:
    messages = build_prompt_messages(req)
    return PromptPreviewResponse(messages=messages, responseSchema=ANALYSIS_RESPONSE_SCHEMA)

@router.post("/refine-translation", response_model=TranslationRefineResponse)
def refine_translation_endpoint(req: TranslationRefineRequest) -> TranslationRefineResponse:
    try:
        return refine_translation(req)
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
