"""Conservative source checks, not a replacement for the BE date extractor."""

import re

from app.schemas import DateCandidate

_FULL_DATE = re.compile(
    r"(?<!\d)(?P<year>\d{4})\s*[년./-]\s*(?P<month>\d{1,2})"
    r"\s*[월./-]\s*(?P<day>\d{1,2})(?:\s*일)?\.?"
)
_MONTH_DAY = re.compile(r"(?P<month>\d{1,2})\s*[월./-]\s*(?P<day>\d{1,2})(?:\s*일)?\.?")
_DAY = re.compile(r"(?P<day>\d{1,2})\s*일")
# Only inherit a year/month across a range separator, never from a school-year title.
_RANGE_GAP = re.compile(r"\s*(?:\([^()\n]*\)\s*)*[~～〜–—]\s*$")
_RANGE_END = re.compile(
    r"^\s*\.?\s*(?:\([^()\n]*\)\s*)*"
    r"(?:\d{1,2}:\d{2}\s*)?[~～〜–—]\s*\d{1,4}\s*[년월일./-]"
)


def source_span(text: str, candidate: DateCandidate) -> tuple[int, int] | None:
    """Accept verified offsets, or a unique occurrence; never guess repeated dates."""
    start, end = candidate.start_offset, candidate.end_offset
    if text[start:end] == candidate.original_text:
        return start, end
    # Java's UTF-16 offsets can differ from Python's after non-BMP characters.
    try:
        encoded = text.encode("utf-16-le")
        prefix = encoded[: start * 2].decode("utf-16-le")
        value = encoded[start * 2 : end * 2].decode("utf-16-le")
        if value == candidate.original_text:
            return len(prefix), len(prefix) + len(value)
    except UnicodeError:
        pass
    if candidate.original_text and text.count(candidate.original_text) == 1:
        start = text.index(candidate.original_text)
        return start, start + len(candidate.original_text)
    return None


def source_date_warning(text: str, candidate: DateCandidate, item_type: str) -> str | None:
    value = candidate.original_text.strip()
    match = _FULL_DATE.fullmatch(value) or _MONTH_DAY.fullmatch(value) or _DAY.fullmatch(value)
    if not match:
        return None
    parts = {key: int(value) for key, value in match.groupdict().items() if value}
    span = source_span(text, candidate)
    if span and "year" not in parts:
        prefix = text[max(0, span[0] - 80) : span[0]]
        anchors = list(_FULL_DATE.finditer(prefix))
        if anchors and _RANGE_GAP.fullmatch(prefix[anchors[-1].end() :]):
            anchor = anchors[-1]
            # Cross-year/month ranges are not resolved here without explicit end values.
            month = parts.get("month", int(anchor["month"]))
            if (month, parts["day"]) >= (int(anchor["month"]), int(anchor["day"])):
                parts.setdefault("year", int(anchor["year"]))
                parts.setdefault("month", int(anchor["month"]))
    if any(getattr(candidate.normalized_date, key) != value for key, value in parts.items()):
        return "SOURCE_DATE_CONFLICT"
    if span and item_type == "deadline" and _RANGE_END.match(text[span[1] : span[1] + 70]):
        return "DEADLINE_RANGE_START"
    return None
