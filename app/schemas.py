from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ExtractedItemType(StrEnum):
    SCHEDULE = "schedule"
    DEADLINE = "deadline"
    CHECKLIST = "checklist"
    REMINDER = "reminder"


class DateStatus(StrEnum):
    CONFIRMED = "confirmed"
    AMBIGUOUS = "ambiguous"
    MISSING = "missing"


class DateCandidate(BaseModel):
    candidate_id: str | None = Field(default=None, alias="candidateId")
    original_text: str = Field(alias="originalText")
    normalized_date: date = Field(alias="normalizedDate")
    start_offset: int = Field(alias="startOffset")
    end_offset: int = Field(alias="endOffset")
    extraction_type: str | None = Field(default=None, alias="extractionType")

    class Config:
        allow_population_by_field_name = True
        populate_by_name = True


class NewsletterExtractionRequest(BaseModel):
    original_text: str = Field(alias="originalText")
    translated_text: str | None = Field(default=None, alias="translatedText")
    language: str = "KO"
    reference_date: date | None = Field(default=None, alias="referenceDate")
    timezone: str = "Asia/Seoul"
    date_candidates: list[DateCandidate] = Field(default_factory=list, alias="dateCandidates")

    class Config:
        allow_population_by_field_name = True
        populate_by_name = True


class SelectedDateCandidate(BaseModel):
    index: int
    candidate_id: str | None = Field(default=None, alias="candidateId")
    original_text: str = Field(alias="originalText")
    normalized_date: date = Field(alias="normalizedDate")

    class Config:
        allow_population_by_field_name = True
        populate_by_name = True


class ExtractedItem(BaseModel):
    type: ExtractedItemType
    title: str
    selected_date_candidate: SelectedDateCandidate | None = Field(
        default=None, alias="selectedDateCandidate"
    )
    date_status: DateStatus = Field(alias="dateStatus")
    datetime: str | None = None
    timezone: str
    evidence_text: str = Field(alias="evidenceText")
    confidence: float = Field(ge=0.0, le=1.0)
    needs_user_confirmation: bool = Field(alias="needsUserConfirmation")
    confirmation_question: str | None = Field(default=None, alias="confirmationQuestion")

    class Config:
        allow_population_by_field_name = True
        populate_by_name = True


class NewsletterExtractionResponse(BaseModel):
    items: list[ExtractedItem]
    meta: dict[str, Any] = Field(default_factory=dict)


class PromptMessage(BaseModel):
    role: str
    content: str


class PromptPreviewResponse(BaseModel):
    messages: list[PromptMessage]
    response_schema: dict[str, Any] = Field(alias="responseSchema")

    class Config:
        allow_population_by_field_name = True
        populate_by_name = True
