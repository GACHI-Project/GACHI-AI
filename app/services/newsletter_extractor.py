import re
from collections.abc import Iterable

from app.schemas import (
    DateCandidate,
    DateStatus,
    ExtractedItem,
    ExtractedItemType,
    NewsletterExtractionRequest,
    NewsletterExtractionResponse,
    SelectedDateCandidate,
)

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
    text = request.original_text or ""
    items = _extract_candidate_backed_items(text, request)
    items.extend(_extract_missing_date_checklists(text, request))
    return NewsletterExtractionResponse(
        items=_dedupe_items(items),
        meta={
            "mode": "rule_based_baseline",
            "dateCandidateCount": len(request.date_candidates),
            "requiresLLMReview": True,
        },
    )


def _extract_candidate_backed_items(
    text: str,
    request: NewsletterExtractionRequest,
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


def _extract_missing_date_checklists(
    text: str,
    request: NewsletterExtractionRequest,
) -> list[ExtractedItem]:
    items = []
    for sentence in _split_sentences(text):
        if not _contains_any(sentence, CHECKLIST_KEYWORDS):
            continue
        if _overlaps_any_candidate(sentence, request.date_candidates):
            continue
        items.append(
            ExtractedItem(
                type=ExtractedItemType.CHECKLIST,
                title=_compact_title(sentence),
                selectedDateCandidate=None,
                dateStatus=DateStatus.MISSING,
                datetime=None,
                timezone=request.timezone,
                evidenceText=sentence,
                confidence=0.55,
                needsUserConfirmation=True,
                confirmationQuestion="이 항목을 체크리스트에 추가할까요?",
            )
        )
    return items


def _classify_item_type(evidence: str) -> ExtractedItemType:
    if _contains_any(evidence, DEADLINE_KEYWORDS):
        return ExtractedItemType.DEADLINE
    if _contains_any(evidence, SCHEDULE_KEYWORDS):
        return ExtractedItemType.SCHEDULE
    if _contains_any(evidence, CHECKLIST_KEYWORDS):
        return ExtractedItemType.CHECKLIST
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
    if item_type == ExtractedItemType.CHECKLIST:
        return 0.74
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
