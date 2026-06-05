from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    model_config = ConfigDict(populate_by_name=True)

    candidate_id: str | None = Field(default=None, alias="candidateId")
    original_text: str = Field(alias="originalText")
    normalized_date: date = Field(alias="normalizedDate")
    start_offset: int = Field(alias="startOffset", ge=0)
    end_offset: int = Field(alias="endOffset", ge=0)
    extraction_type: str | None = Field(default=None, alias="extractionType")

    @model_validator(mode="after")
    def validate_offsets(self) -> "DateCandidate":
        if self.end_offset < self.start_offset:
            raise ValueError("endOffset must be greater than or equal to startOffset")
        return self


class NewsletterAnalysisRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    original_text: str = Field(alias="originalText")
    translated_text: str | None = Field(default=None, alias="translatedText")
    language: str = "KO"
    reference_date: date | None = Field(default=None, alias="referenceDate")
    timezone: str = "Asia/Seoul"
    date_candidates: list[DateCandidate] = Field(default_factory=list, alias="dateCandidates")


class NewsletterExtractionRequest(NewsletterAnalysisRequest):
    pass


class SelectedDateCandidate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    index: int
    candidate_id: str | None = Field(default=None, alias="candidateId")
    original_text: str = Field(alias="originalText")
    normalized_date: date = Field(alias="normalizedDate")


class ExtractedItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

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


class NewsletterExtractionResponse(BaseModel):
    items: list[ExtractedItem]
    meta: dict[str, Any] = Field(default_factory=dict)

class ConversationTopic(BaseModel):
    topic: str

class NewsletterAnalysisResponse(BaseModel):
    title: str
    summary: str
    items: list[ExtractedItem]
    conversation_topics: list[ConversationTopic] = Field(
        default_factory=list, alias="conversationTopics"
    )
    meta: dict[str, Any] = Field(default_factory=dict)


class PromptMessage(BaseModel):
    role: str
    content: str


class PromptPreviewResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    messages: list[PromptMessage]
    response_schema: dict[str, Any] = Field(alias="responseSchema")


class ChatMessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatLanguage(StrEnum):
    KO = "KO"
    US = "US"
    ZH = "ZH"
    VI = "VI"


class ChatType(StrEnum):
    GENERAL = "GENERAL"
    DOCUMENT = "DOCUMENT"  # 추후 문서 챗봇


class ChatMessageItem(BaseModel):
    role: ChatMessageRole
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessageItem] = []
    language: ChatLanguage = ChatLanguage.KO
    chat_type: ChatType = ChatType.GENERAL


class ChatResponse(BaseModel):
    reply: str
