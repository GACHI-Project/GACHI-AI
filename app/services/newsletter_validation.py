"""Validate model-selected dates without discarding otherwise useful analysis."""

from datetime import date, datetime

from app.schemas import DateStatus, NewsletterAnalysisRequest, NewsletterAnalysisResponse


def normalize_analysis_dates(
    request: NewsletterAnalysisRequest, response: NewsletterAnalysisResponse
) -> NewsletterAnalysisResponse:
    items = []
    warnings = []
    for index, original in enumerate(response.items):
        item = original.model_copy(deep=True)
        if item.date_status == DateStatus.MISSING:
            item.selected_date_candidate = None
            item.datetime = None
            item.needs_user_confirmation = False
            item.confirmation_question = None
        elif item.date_status == DateStatus.AMBIGUOUS:
            item.selected_date_candidate = None
            item.datetime = None
            item.needs_user_confirmation = True
            item.confirmation_question = item.confirmation_question or "날짜를 확인해 주세요."
        else:
            selected = item.selected_date_candidate
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
            if not valid:
                item.date_status = DateStatus.AMBIGUOUS
                item.datetime = None
                item.selected_date_candidate = None
                item.needs_user_confirmation = True
                item.confirmation_question = "원문의 날짜와 날짜 후보가 일치하는지 확인해 주세요."
                warnings.append({"itemIndex": index, "code": "DATE_CANDIDATE_MISMATCH"})
        items.append(item)

    meta = dict(response.meta)
    meta["dateValidationWarnings"] = warnings
    # Date validation must not clear review requests raised for other reasons.
    meta["requiresLLMReview"] = bool(meta.get("requiresLLMReview")) or any(
        item.date_status == DateStatus.AMBIGUOUS for item in items
    )
    return response.model_copy(update={"items": items, "meta": meta})


def _date_part(value: str | None) -> date | None:
    if not value:
        return None
    try:
        if len(value) == 10:
            return date.fromisoformat(value)
        if len(value) > 10 and value[10] == "T":
            return datetime.fromisoformat(value).date()
    except ValueError:
        pass
    return None
