"""Strict evaluation inputs. Gold labels must never be used to synthesize OCR text."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.schemas import NewsletterAnalysisRequest
from app.services.newsletter_document import LoadedDocument

SCHEMA_VERSION = "gachi-newsletter-evaluation-v3"
BE_SCHEMA_VERSION = "gachi-newsletter-ocr-v1"
MIME_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


@dataclass(frozen=True)
class LabelItem:
    type: str
    title: str
    date_status: str
    datetime: str | None
    evidence_text: str | None = None
    selected_date_candidate_id: str | None = None
    end_datetime: str | None = None
    period_start_datetime: str | None = None
    timezone: str = "Asia/Seoul"
    needs_user_confirmation: bool | None = None
    checklist_items: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class LabelSample:
    sample_id: str
    source_file: str | None
    request: NewsletterAnalysisRequest
    expected_title: str | None
    expected_summary: str | None
    expected_items: list[LabelItem]
    source_files: list[dict[str, Any]] = field(default_factory=list)
    base_dir: Path = Path(".")
    metadata: dict[str, Any] = field(default_factory=dict)
    dataset_sha256: str = ""


class EvaluationInputError(ValueError):
    """Only safe sample identifiers and fixed codes may be printed by the CLI."""

    def __init__(self, sample_id: str, code: str):
        super().__init__(f"{sample_id}: {code}")


def read_records(path: Path) -> list[dict[str, Any]]:
    paths = sorted(path.glob("*.json")) if path.is_dir() else [path]
    records = []
    for file in paths:
        data = json.loads(file.read_text(encoding="utf-8-sig"))
        if not isinstance(data, (dict, list)):
            raise ValueError("INVALID_DATASET")
        rows = data if isinstance(data, list) else data.get("samples", [data])
        if not isinstance(rows, list):
            raise ValueError("INVALID_DATASET: samples must be an array")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("INVALID_SAMPLE: samples must be objects")
            records.append(
                {
                    **row,
                    "_baseDir": file.resolve().parent,
                    "_fileStem": file.stem,
                    "_datasetSha256": sha256(file.read_bytes()),
                }
            )
    if not records:
        raise ValueError("EMPTY_DATASET")
    return records


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def convert_offsets(request: dict[str, Any], *, encoding: str) -> dict[str, Any]:
    """BE offsets are UTF-16 units; canonical evaluation inputs use Python code points."""
    text = request.get("originalText")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("MISSING_OCR_TEXT: 실제 BE originalText가 필요합니다")
    if encoding not in {"utf-16", "codepoint"}:
        raise ValueError("INVALID_OFFSET_ENCODING")
    candidates = []
    ids = set()
    for raw in request.get("dateCandidates", []):
        candidate = dict(raw)
        candidate_id = candidate.get("candidateId")
        if not isinstance(candidate_id, str) or not candidate_id or candidate_id in ids:
            raise ValueError("INVALID_CANDIDATE_ID")
        ids.add(candidate_id)
        start, end = candidate.get("startOffset"), candidate.get("endOffset")
        if type(start) is not int or type(end) is not int or not 0 <= start < end:
            raise ValueError("INVALID_CANDIDATE_OFFSETS")
        if encoding == "utf-16":
            encoded = text.encode("utf-16-le")
            if end * 2 > len(encoded):
                raise ValueError("INVALID_CANDIDATE_OFFSETS")
            try:
                prefix = encoded[: start * 2].decode("utf-16-le")
                span = encoded[start * 2 : end * 2].decode("utf-16-le")
            except UnicodeError as exc:
                raise ValueError("INVALID_UTF16_BOUNDARY") from exc
            start, end = len(prefix), len(prefix) + len(span)
        if end > len(text) or text[start:end] != candidate.get("originalText"):
            raise ValueError("CANDIDATE_TEXT_MISMATCH")
        candidate.update(startOffset=start, endOffset=end)
        candidates.append(candidate)
    return {**request, "dateCandidates": candidates}


def parse_sample(raw: dict[str, Any], index: int = 1, *, allow_drafts: bool = False) -> LabelSample:
    if raw.get("schemaVersion") not in (None, SCHEMA_VERSION):
        raise ValueError("UNSUPPORTED_LABEL_SCHEMA")
    sample_id = str(
        raw.get("sampleId") or raw.get("documentId") or raw.get("_fileStem") or f"sample_{index}"
    )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", sample_id):
        raise ValueError("INVALID_SAMPLE_ID")
    metadata = raw.get("metadata") or {}
    if not isinstance(metadata, dict) or metadata.get("annotationStatus", "reviewed") not in {
        "draft",
        "reviewed",
    }:
        raise ValueError("INVALID_ANNOTATION_STATUS")
    if metadata.get("annotationStatus", "reviewed") != "reviewed" and not allow_drafts:
        raise ValueError("UNREVIEWED_LABEL: 검수 후 reviewed로 표시하거나 --allow-drafts 사용")
    request_data = raw.get("input") or raw.get("request")
    if request_data is None:
        # Explicit legacy input only. Do not infer originalText or referenceDate from gold labels.
        request_data = {
            key: raw[key]
            for key in (
                "originalText",
                "translatedText",
                "language",
                "referenceDate",
                "timezone",
                "dateCandidates",
            )
            if key in raw
        }
    if not isinstance(request_data, dict):
        raise ValueError("INVALID_INPUT")
    if not request_data.get("referenceDate"):
        raise ValueError("MISSING_REFERENCE_DATE: documentDate는 업로드 기준일이 아닙니다")
    if not isinstance(request_data.get("dateCandidates"), list):
        raise ValueError("MISSING_DATE_CANDIDATES: 후보가 없으면 빈 배열을 지정하세요")
    request_data = convert_offsets(request_data, encoding=raw.get("offsetEncoding", "codepoint"))
    request = NewsletterAnalysisRequest.model_validate(request_data)
    if request.documents:
        raise ValueError("REMOTE_DOCUMENTS_NOT_ALLOWED: 로컬 sourceFiles를 사용하세요")
    ZoneInfo(request.timezone)
    expected = raw.get("expected")
    if expected is None and isinstance(raw.get("labels"), list):
        expected = {
            "title": raw.get("documentTitle"),
            "summary": raw.get("summary"),
            "items": raw["labels"],
        }
    if not isinstance(expected, dict) or not isinstance(expected.get("items"), list):
        raise ValueError("MISSING_EXPECTED_ITEMS: 정답이 없으면 빈 배열을 명시하세요")
    sources = raw.get("sourceFiles") or []
    if not isinstance(sources, list):
        raise ValueError("INVALID_SOURCE_FILES")
    for source in sources:
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("path"), str)
            or not source["path"].strip()
        ):
            raise ValueError("INVALID_SOURCE_PATH")
        if source.get("sha256") and not re.fullmatch(r"[0-9a-f]{64}", source["sha256"]):
            raise ValueError("INVALID_SOURCE_HASH")
    return LabelSample(
        sample_id=str(
            raw.get("sampleId")
            or raw.get("documentId")
            or raw.get("_fileStem")
            or f"sample_{index}"
        ),
        source_file=raw.get("sourceFile"),
        request=request,
        expected_title=expected.get("title"),
        expected_summary=expected.get("summary"),
        expected_items=[parse_label_item(item) for item in expected["items"]],
        source_files=raw.get("sourceFiles") or [],
        base_dir=Path(raw.get("_baseDir", ".")),
        metadata=metadata,
        dataset_sha256=raw.get("_datasetSha256", ""),
    )


def parse_label_item(raw: dict[str, Any], *, validate: bool = True) -> LabelItem:
    if not isinstance(raw, dict):
        raise ValueError("INVALID_EXPECTED_ITEM")
    selected = raw.get("selectedDateCandidate") or {}
    item = LabelItem(
        type=raw.get("type", ""),
        title=raw.get("title", ""),
        date_status=raw.get("dateStatus", ""),
        datetime=raw.get("datetime", raw.get("date")),
        evidence_text=raw.get("evidenceText"),
        selected_date_candidate_id=raw.get("selectedDateCandidateId")
        or selected.get("candidateId"),
        end_datetime=raw.get("endDatetime"),
        period_start_datetime=raw.get("periodStartDatetime"),
        timezone=raw.get("timezone", "Asia/Seoul"),
        needs_user_confirmation=raw.get("needsUserConfirmation"),
        checklist_items=raw.get("checklistItems"),
    )
    if validate:
        _validate_label(item)
    return item


def _validate_label(item: LabelItem) -> None:
    if (
        item.type not in {"schedule", "deadline", "reminder"}
        or not isinstance(item.title, str)
        or not item.title.strip()
    ):
        raise ValueError("INVALID_LABEL_TYPE_OR_TITLE")
    if item.date_status not in {"confirmed", "missing", "ambiguous"}:
        raise ValueError("INVALID_LABEL_DATE_STATUS")
    ZoneInfo(item.timezone)
    for value in (item.datetime, item.end_datetime, item.period_start_datetime):
        if value is not None:
            if not isinstance(value, str):
                raise ValueError("INVALID_LABEL_DATETIME")
            if len(value) != 10 and not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", value):
                raise ValueError("INVALID_LABEL_DATETIME")
            date.fromisoformat(value) if len(value) == 10 else datetime.fromisoformat(value)
    if item.date_status == "confirmed" and (
        not item.datetime or item.needs_user_confirmation is not False
    ):
        raise ValueError("INVALID_CONFIRMED_LABEL")
    if item.date_status != "confirmed" and any(
        (item.datetime, item.end_datetime, item.period_start_datetime)
    ):
        raise ValueError("UNCONFIRMED_LABEL_WITH_DATE")
    if item.date_status == "ambiguous" and item.needs_user_confirmation is not True:
        raise ValueError("AMBIGUOUS_LABEL_REQUIRES_CONFIRMATION")
    if item.type == "reminder" and (
        item.date_status != "missing" or item.needs_user_confirmation is not False
    ):
        raise ValueError("INVALID_REMINDER_LABEL")
    if item.date_status == "missing" and item.type != "reminder":
        raise ValueError("MISSING_DATE_REQUIRES_REMINDER")
    if item.end_datetime and item.type != "schedule":
        raise ValueError("END_DATETIME_REQUIRES_SCHEDULE")
    if item.period_start_datetime and item.type != "deadline":
        raise ValueError("PERIOD_START_REQUIRES_DEADLINE")
    for extra, is_end in ((item.end_datetime, True), (item.period_start_datetime, False)):
        if extra and item.datetime:
            values = []
            for value in (item.datetime, extra):
                parsed = datetime.fromisoformat(value)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=ZoneInfo(item.timezone))
                values.append(parsed.astimezone(ZoneInfo(item.timezone)))
            if len(extra) == 10 or len(item.datetime) == 10:
                values = [value.date() for value in values]
            if (is_end and values[1] < values[0]) or (not is_end and values[1] > values[0]):
                raise ValueError("INVALID_LABEL_PERIOD_ORDER")
    if item.checklist_items is not None:
        if not isinstance(item.checklist_items, list):
            raise ValueError("INVALID_CHECKLIST")
        for action in item.checklist_items:
            if (
                not isinstance(action, dict)
                or not isinstance(action.get("content"), str)
                or not action["content"].strip()
            ):
                raise ValueError("INVALID_CHECKLIST_ACTION")
            if action.get("detail") is not None and not isinstance(action["detail"], str):
                raise ValueError("INVALID_CHECKLIST_DETAIL")
            accepted = action.get("acceptedContents", [])
            if not isinstance(accepted, list) or any(not isinstance(s, str) for s in accepted):
                raise ValueError("INVALID_CHECKLIST_ACCEPTED_CONTENTS")
            for key in ("contentPatterns", "detailPatterns"):
                patterns = action.get(key, [])
                if not isinstance(patterns, list) or any(
                    not isinstance(p, str) or not p.strip() for p in patterns
                ):
                    raise ValueError("INVALID_CHECKLIST_PATTERN")
                for pattern in patterns:
                    try:
                        re.compile(pattern)
                    except re.error as exc:
                        raise ValueError("INVALID_CHECKLIST_PATTERN") from exc


def load_samples(path: Path, *, allow_drafts: bool = False) -> list[LabelSample]:
    samples = []
    for index, raw in enumerate(read_records(path), 1):
        try:
            samples.append(parse_sample(raw, index, allow_drafts=allow_drafts))
        except (ValueError, KeyError, TypeError) as exc:
            identifier = str(raw.get("sampleId") or raw.get("documentId") or f"sample_{index}")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", identifier):
                identifier = f"sample_{index}"
            code = str(exc).split(":", 1)[0]
            if not re.fullmatch(r"[A-Z_]+", code):
                code = "INVALID_SAMPLE"
            raise EvaluationInputError(identifier, code) from None
    if len({sample.sample_id for sample in samples}) != len(samples):
        raise ValueError("DUPLICATE_SAMPLE_ID")
    return samples


def load_local_documents(sample: LabelSample, *, max_bytes: int) -> list[LoadedDocument]:
    if not sample.source_files:
        raise ValueError("MISSING_SOURCE_FILES")
    loaded = []
    remaining = max_bytes
    for source in sample.source_files:
        file = sample.base_dir / source["path"]
        mime = MIME_TYPES.get(file.suffix.lower())
        if not mime:
            raise ValueError("UNSUPPORTED_SOURCE_TYPE")
        if file.stat().st_size > remaining:
            raise ValueError("DOCUMENT_SIZE_LIMIT")
        with file.open("rb") as stream:
            content = stream.read(remaining + 1)
        if not content or len(content) > remaining:
            raise ValueError("DOCUMENT_SIZE_LIMIT_OR_EMPTY")
        if source.get("sha256") and source["sha256"] != sha256(content):
            raise ValueError("SOURCE_FILE_CHANGED")
        remaining -= len(content)
        loaded.append(
            LoadedDocument(
                file_name=f"page-{len(loaded) + 1}{file.suffix.lower()}",
                mime_type=mime,
                content=content,
            )
        )
    return loaded


def merge_be_result(raw: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    sample_id = raw.get("sampleId") or raw.get("documentId")
    if result.get("schemaVersion") != BE_SCHEMA_VERSION:
        raise ValueError("UNSUPPORTED_BE_SCHEMA")
    if sample_id != result.get("sampleId"):
        raise ValueError("BE_SAMPLE_ID_MISMATCH")
    if result.get("status") != "SUCCESS":
        raise ValueError("BE_OCR_NOT_SUCCESS: PARTIAL/FAILED 결과는 평가에 사용할 수 없습니다")
    request = convert_offsets(result["input"], encoding="utf-16")
    metadata = {
        **raw.get("metadata", {}),
        "inputStatus": "ready",
        "ocrProcessingVersion": result.get("processingVersion"),
        "ocrFingerprint": result.get("fingerprint"),
    }
    merged = {key: value for key, value in raw.items() if not key.startswith("_")}
    return {
        **merged,
        "input": request,
        "offsetEncoding": "codepoint",
        "sourceFiles": result.get("sourceFiles", []),
        "metadata": metadata,
    }
