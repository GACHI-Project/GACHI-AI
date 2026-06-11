import logging
import re
from collections.abc import Iterable

from app.config import get_openai_settings
from app.schemas import (
    ChecklistItem,
    DateCandidate,
    DateStatus,
    ExtractedItem,
    ExtractedItemType,
    NewsletterAnalysisRequest,
    NewsletterAnalysisResponse,
    NewsletterExtractionRequest,
    NewsletterExtractionResponse,
    SelectedDateCandidate,
)
from app.services.openai_adapter import OpenAINewsletterAdapter

logger = logging.getLogger(__name__)

DEADLINE_KEYWORDS = (
    "마감",
    "까지",
    "제출",
    "신청",
    "접수",
    "납부",
    "등록",
    "동의서",
    "회신",
)
SCHEDULE_KEYWORDS = (
    "일정",
    "행사",
    "체험",
    "상담",
    "설명회",
    "교육",
    "운영",
    "참여",
    "개최",
    "방문",
    "학습",
)
CHECKLIST_KEYWORDS = (
    "준비물",
    "지참",
    "가져",
    "챙겨",
    "확인",
    "작성",
    "서명",
    "제출",
)


def extract_newsletter_items(
    request: NewsletterExtractionRequest,
) -> NewsletterExtractionResponse:
    items = _extract_items(request)
    return NewsletterExtractionResponse(
        items=items,
        meta=_build_meta(request),
    )


def analyze_newsletter(
    request: NewsletterAnalysisRequest,
) -> NewsletterAnalysisResponse:
    settings = get_openai_settings()
    if settings.enabled:
        logger.info("[NewsletterAnalysis] OpenAI 분석 모드로 실행합니다. model=%s", settings.model)
        response = OpenAINewsletterAdapter(settings).analyze(request)
        meta = dict(response.meta)
        meta.update(
            {
                "mode": "openai",
                "model": settings.model,
                "dateCandidateCount": len(request.date_candidates),
                "requiresLLMReview": False,
            }
        )
        return response.model_copy(update={"meta": meta})

    items = _extract_items(request)
    return NewsletterAnalysisResponse(
        title=_extract_document_title(request),
        summary=_summarize_document(request, items),
        items=items,
        meta=_build_meta(request),
    )


def _extract_items(
    request: NewsletterAnalysisRequest,
) -> list[ExtractedItem]:
    text = request.original_text or ""
    items = _extract_candidate_backed_items(text, request)
    items = _dedupe_items(items)
    _attach_checklist_items(text, request, items)
    return items


def _build_meta(request: NewsletterAnalysisRequest) -> dict[str, object]:
    return {
        "mode": "rule_based_baseline",
        "dateCandidateCount": len(request.date_candidates),
        "requiresLLMReview": True,
        "retainedDateCandidateInput": True,
        "retainedItemResponse": True,
    }


def _extract_candidate_backed_items(
    text: str,
    request: NewsletterAnalysisRequest,
) -> list[ExtractedItem]:
    items = []
    for index, candidate in enumerate(request.date_candidates):
        evidence = _evidence_window(text, candidate)
        item_type = _classify_item_type(evidence)
        selected = SelectedDateCandidate(
            index=index,
            candidateId=candidate.candidate_id,
            originalText=candidate.original_text,
            normalizedDate=candidate.normalized_date,
        )
        items.append(
            ExtractedItem(
                type=item_type,
                title=_build_title(evidence, item_type),
                selectedDateCandidate=selected,
                dateStatus=DateStatus.CONFIRMED,
                datetime=candidate.normalized_date.isoformat(),
                timezone=request.timezone,
                evidenceText=evidence,
                confidence=_confidence_for(item_type),
                needsUserConfirmation=False,
                confirmationQuestion=None,
            )
        )
    return items


# def _extract_missing_date_checklists(
#     text: str,
#     request: NewsletterAnalysisRequest,
# ) -> list[ExtractedItem]:
#     items = []
#     for sentence in _split_sentences(text):
#         if not _contains_any(sentence, CHECKLIST_KEYWORDS):
#             continue
#         if _overlaps_any_candidate(sentence, request.date_candidates):
#             continue
#         items.append(
#             ExtractedItem(
#                 type=ExtractedItemType.CHECKLIST,
#                 title=_compact_title(sentence),
#                 selectedDateCandidate=None,
#                 dateStatus=DateStatus.MISSING,
#                 datetime=None,
#                 timezone=request.timezone,
#                 evidenceText=sentence,
#                 confidence=0.55,
#                 needsUserConfirmation=True,
#                 confirmationQuestion="이 항목을 체크리스트에 추가할까요?",
#             )
#         )
#     return items


def _attach_checklist_items(
    text: str,
    request: NewsletterAnalysisRequest,
    items: list[ExtractedItem],
) -> None:
    if not items:
        return

    # 각 item의 evidence_text가 본문에서 등장하는 위치(대략적인 오프셋)를 미리 계산
    item_positions = []
    for item in items:
        pos = text.find(item.evidence_text) if item.evidence_text else -1
        item_positions.append(pos if pos >= 0 else len(text))

    for sentence in _split_sentences(text):
        if not _contains_any(sentence, CHECKLIST_KEYWORDS):
            continue
        if _overlaps_any_candidate(sentence, request.date_candidates):
            continue

        sentence_pos = text.find(sentence)
        if sentence_pos < 0:
            sentence_pos = 0

        # 본문 상 위치가 가장 가까운 일정 item을 선택
        nearest_index = min(
            range(len(items)),
            key=lambda i: abs(item_positions[i] - sentence_pos),
        )
        target_item = items[nearest_index]

        checklist_item = ChecklistItem(
            content=_compact_title(sentence),
            detail=sentence,
        )

        # 동일한 content가 이미 있으면 중복 추가하지 않음
        if any(
            existing.content == checklist_item.content for existing in target_item.checklist_items
        ):
            continue

        target_item.checklist_items.append(checklist_item)


def _classify_item_type(evidence: str) -> ExtractedItemType:
    if _contains_any(evidence, DEADLINE_KEYWORDS):
        return ExtractedItemType.DEADLINE
    if _contains_any(evidence, SCHEDULE_KEYWORDS):
        return ExtractedItemType.SCHEDULE
    return ExtractedItemType.REMINDER


def _build_title(evidence: str, item_type: ExtractedItemType) -> str:
    title = _compact_title(evidence)
    if item_type == ExtractedItemType.DEADLINE and "마감" not in title:
        return f"{title} 마감"
    return title


def _compact_title(text: str) -> str:
    title = re.sub(r"\s+", " ", text).strip(" \n\t-:：")
    if len(title) <= 40:
        return title
    return title[:39].rstrip() + "..."


def _evidence_window(text: str, candidate: DateCandidate) -> str:
    if not text:
        return candidate.original_text

    start = max(candidate.start_offset - 45, 0)
    end = min(candidate.end_offset + 70, len(text))
    window = text[start:end]
    left_break = max(window.rfind("\n", 0, candidate.start_offset - start), 0)
    right_break = window.find("\n", candidate.end_offset - start)
    if right_break == -1:
        right_break = len(window)
    evidence = window[left_break:right_break]
    return re.sub(r"\s+", " ", evidence).strip() or candidate.original_text


def _split_sentences(text: str) -> Iterable[str]:
    for part in re.split(r"[\n.!?。]+", text):
        sentence = re.sub(r"\s+", " ", part).strip(" -:：")
        if sentence:
            yield sentence


def _overlaps_any_candidate(sentence: str, candidates: list[DateCandidate]) -> bool:
    return any(candidate.original_text in sentence for candidate in candidates)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _confidence_for(item_type: ExtractedItemType) -> float:
    if item_type in (ExtractedItemType.DEADLINE, ExtractedItemType.SCHEDULE):
        return 0.82
    return 0.62


def _dedupe_items(items: list[ExtractedItem]) -> list[ExtractedItem]:
    seen = set()
    result = []
    for item in items:
        key = (item.type, item.datetime, item.evidence_text)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _extract_document_title(request: NewsletterAnalysisRequest) -> str:
    for line in request.original_text.splitlines():
        title = re.sub(r"\s+", " ", line).strip(" -:\t")
        if title:
            return title[:80].rstrip()
    return "가정통신문"


def _summarize_document(
    request: NewsletterAnalysisRequest,
    items: list[ExtractedItem],
) -> str:
    translated = (request.translated_text or "").strip()
    text = translated or request.original_text
    sentences = list(_split_sentences(text))
    if sentences:
        summary = " ".join(sentences[:2])
        if len(summary) > 180:
            return summary[:179].rstrip() + "..."
        return summary
    if items:
        return f"추출된 주요 항목 {len(items)}건을 확인해야 합니다."
    return "분석할 본문 내용이 충분하지 않습니다."
