"""Validate model-selected dates without discarding otherwise useful analysis."""

import re
from datetime import date, datetime

from app.schemas import (
    DateCandidate,
    DateStatus,
    NewsletterAnalysisRequest,
    NewsletterAnalysisResponse,
)
from app.services.newsletter_date_source import source_date_warning, source_span

DOCUMENT_ONLY_DATE = "DOCUMENT_ONLY_DATE"


def normalize_analysis_dates(
    request: NewsletterAnalysisRequest,
    response: NewsletterAnalysisResponse,
    *,
    documents_attached: bool = False,
) -> NewsletterAnalysisResponse:
    items = []
    warnings = []
    for index, original in enumerate(response.items):
        item = original.model_copy(deep=True)
        if item.date_status == DateStatus.MISSING:
            item.selected_date_candidate = None
            item.datetime = None
            item.end_datetime = None
            item.period_start_datetime = None
            item.needs_user_confirmation = False
            item.confirmation_question = None
        elif item.date_status == DateStatus.AMBIGUOUS:
            item.selected_date_candidate = None
            item.datetime = None
            item.end_datetime = None
            item.period_start_datetime = None
            item.needs_user_confirmation = True
            item.confirmation_question = item.confirmation_question or "날짜를 확인해 주세요."
        else:
            selected = item.selected_date_candidate
            # 조건 3가지를 모두 만족할 때만 confirmed를 유지한다.
            #   1) 원본 문서가 실제로 첨부되어 분석됨 (첨부 실패 시에는 기존 규칙 그대로)
            #   2) 후보를 고르지 않음 (후보를 골랐는데 틀린 경우는 아래 기존 검증으로 강등)
            #   3) datetime이 올바른 날짜 형식
            if documents_attached and selected is None and _date_part(item.datetime) is not None:
                warnings.append({"itemIndex": index, "code": DOCUMENT_ONLY_DATE})
            else:
                candidate = (
                    request.date_candidates[selected.index]
                    if selected and 0 <= selected.index < len(request.date_candidates)
                    else None
                )
                valid = (
                    candidate is not None
                    and selected is not None
                    and selected.candidate_id == candidate.candidate_id
                    and selected.original_text == candidate.original_text
                    and selected.normalized_date == candidate.normalized_date
                    and _date_part(item.datetime) == candidate.normalized_date
                )
                warning = (
                    source_date_warning(request.original_text, candidate, item.type)
                    if valid
                    else "DATE_CANDIDATE_MISMATCH"
                )
                if warning:
                    item.date_status = DateStatus.AMBIGUOUS
                    item.datetime = None
                    item.end_datetime = None
                    item.period_start_datetime = None
                    item.selected_date_candidate = None
                    item.needs_user_confirmation = True
                    item.confirmation_question = (
                        "원문의 날짜와 날짜 후보가 일치하는지 확인해 주세요."
                    )
                    warnings.append({"itemIndex": index, "code": warning})
            if item.date_status == DateStatus.CONFIRMED:
                for field, allowed_type, code in (
                    ("end_datetime", "schedule", "INVALID_END_DATETIME"),
                    ("period_start_datetime", "deadline", "INVALID_PERIOD_START_DATETIME"),
                ):
                    value = getattr(item, field)
                    if value is None:
                        continue
                    auxiliary = _parse_datetime(value)
                    supported_date = documents_attached or (
                        auxiliary is not None
                        and any(
                            candidate.normalized_date == auxiliary.date()
                            and source_span(request.original_text, candidate) is not None
                            and source_date_warning(request.original_text, candidate, "schedule")
                            is None
                            and (
                                len(value) == 10
                                or _source_supports_time(
                                    request.original_text,
                                    request.date_candidates,
                                    candidate,
                                    auxiliary,
                                )
                            )
                            for candidate in request.date_candidates
                        )
                    )
                    ordered = _is_ordered(item.datetime, value, field)
                    if item.type != allowed_type or not supported_date or not ordered:
                        setattr(item, field, None)
                        warnings.append({"itemIndex": index, "code": code})
        items.append(item)

    meta = dict(response.meta)
    meta["dateValidationWarnings"] = warnings
    # Date validation must not clear review requests raised for other reasons.
    meta["requiresLLMReview"] = bool(meta.get("requiresLLMReview")) or any(
        item.date_status == DateStatus.AMBIGUOUS for item in items
    )
    return response.model_copy(update={"items": items, "meta": meta})


def _date_part(value: str | None) -> date | None:
    parsed = _parse_datetime(value)
    return parsed.date() if parsed is not None else None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if len(value) == 10:
            return datetime.combine(date.fromisoformat(value), datetime.min.time())
        if len(value) > 10 and value[10] == "T":
            return datetime.fromisoformat(value)
    except ValueError:
        pass
    return None


def _is_ordered(primary_value: str | None, auxiliary_value: str, field: str) -> bool:
    primary = _parse_datetime(primary_value)
    auxiliary = _parse_datetime(auxiliary_value)
    if primary is None or auxiliary is None:
        return False
    if len(primary_value or "") == 10 or len(auxiliary_value) == 10:
        if primary.date() == auxiliary.date():
            return True
        return (
            auxiliary.date() > primary.date()
            if field == "end_datetime"
            else auxiliary.date() < primary.date()
        )
    if (primary.tzinfo is None) != (auxiliary.tzinfo is None):
        return False
    return auxiliary >= primary if field == "end_datetime" else auxiliary <= primary


def _source_supports_time(
    text: str, candidates: list[DateCandidate], candidate: DateCandidate, value: datetime
) -> bool:
    span = source_span(text, candidate)
    if span is None:
        return False
    next_starts = [
        other_span[0]
        for other in candidates
        if other is not candidate
        and (other_span := source_span(text, other)) is not None
        and other_span[0] > span[0]
    ]
    end = min([span[1] + 100, *next_starts])
    evidence = text[span[0] : end]
    hour, minute = value.hour, value.minute
    seconds = r"(?::00)?" if value.second == 0 else rf":0?{value.second}"
    numeric = rf"(?<!\d)0?{hour}:0?{minute}{seconds}(?![:\d])"
    if re.search(numeric, evidence):
        return True
    meridiem = "오전" if hour < 12 else "오후"
    twelve_hour = hour % 12 or 12
    minute_part = r"(?:\s*0?0\s*분)?" if minute == 0 else rf"\s*{minute}\s*분"
    korean = rf"(?<!\d)(?:(?:{meridiem}\s*{twelve_hour})|{hour})\s*시{minute_part}"
    return bool(re.search(korean, evidence))
