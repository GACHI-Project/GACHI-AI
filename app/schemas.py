from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExtractedItemType(StrEnum):
    SCHEDULE = "schedule"
    DEADLINE = "deadline"
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


class ChecklistItem(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    content_i18n: dict[str, str] = Field(default_factory=dict, alias="contentI18n")
    detail: str | None = Field(default=None, max_length=500)
    detail_i18n: dict[str, str] = Field(default_factory=dict, alias="detailI18n")


class ExtractedItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: ExtractedItemType
    title: str
    title_i18n: dict[str, str] = Field(default_factory=dict, alias="titleI18n")
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
    checklist_items: list[ChecklistItem] = Field(default_factory=list, alias="checklistItems")


class NewsletterExtractionResponse(BaseModel):
    items: list[ExtractedItem]
    meta: dict[str, Any] = Field(default_factory=dict)


class ConversationTopic(BaseModel):
    topic: str = Field(min_length=1, max_length=200)


class NewsletterAnalysisResponse(BaseModel):
    title: str
    title_i18n: dict[str, str] = Field(default_factory=dict, alias="titleI18n")
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
    DOCUMENT = "DOCUMENT"  # 문서 챗봇


class ChatMessageItem(BaseModel):
    role: ChatMessageRole
    content: str


# 문서 챗봇에서 BE가 매 요청마다 전달하는 문서 컨텍스트.
class ChatDocumentContext(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    newsletter_id: int | None = Field(default=None, alias="newsletterId")
    title: str | None = None
    summary: str | None = None
    original_text: str = Field(alias="originalText")


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    message: str
    history: list[ChatMessageItem] = []
    language: ChatLanguage = ChatLanguage.KO
    chat_type: ChatType = Field(default=ChatType.GENERAL, alias="chatType")
    document: ChatDocumentContext | None = None


class ChatResponse(BaseModel):
    reply: str


class RefineFieldInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    ko_text: str = Field(alias="koText")
    translated_text: str = Field(min_length=1, alias="translatedText")


class TranslationRefineRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    original_text: str = Field(alias="originalText")
    language: str = "KO"
    fields: list[RefineFieldInput] = Field(default_factory=list)


class RefineFieldOutput(BaseModel):
    id: str
    text: str = Field(min_length=1)


class TranslationRefineResponse(BaseModel):
    fields: list[RefineFieldOutput] = Field(default_factory=list)


# 문화 맥락 안내 (Cultural Guide)
class CulturalGuideFaqCandidate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    faq_id: int = Field(alias="faqId")
    category: str
    question: str = Field(min_length=1)


class CulturalGuideRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    original_text: str = Field(alias="originalText")
    title: str | None = None
    summary: str | None = None
    faq_candidates: list[CulturalGuideFaqCandidate] = Field(
        default_factory=list, alias="faqCandidates"
    )


class SelectedCulturalGuide(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    faq_id: int = Field(alias="faqId")
    # relevanceReason은 화면에 노출X. 프롬프트 품질 점검/로깅용.
    relevance_reason: str = Field(default="", alias="relevanceReason")


class CulturalGuideResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    selected_faqs: list[SelectedCulturalGuide] = Field(default_factory=list, alias="selectedFaqs")
