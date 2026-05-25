from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.schemas import NewsletterAnalysisRequest, NewsletterAnalysisResponse  # noqa: E402
from app.services.newsletter_extractor import analyze_newsletter  # noqa: E402


@dataclass(frozen=True)
class LabelItem:
    type: str
    title: str
    date_status: str
    datetime: str | None
    evidence_text: str | None
    selected_date_candidate_id: str | None


@dataclass(frozen=True)
class LabelSample:
    sample_id: str
    source_file: str | None
    request: NewsletterAnalysisRequest
    expected_title: str | None
    expected_summary: str | None
    expected_items: list[LabelItem]


@dataclass(frozen=True)
class ItemMatch:
    expected_index: int
    predicted_index: int
    score: float
    type_match: bool
    title_similarity: float
    date_status_match: bool
    datetime_match: bool


@dataclass(frozen=True)
class SampleReport:
    sample_id: str
    title_match: bool | None
    title_similarity: float | None
    summary_match: bool | None
    summary_similarity: float | None
    expected_item_count: int
    predicted_item_count: int
    matched_item_count: int
    item_precision: float
    item_recall: float
    item_f1: float
    type_accuracy: float | None
    datetime_accuracy: float | None
    date_status_accuracy: float | None
    title_similarity_avg: float | None
    missing_expected_items: list[dict[str, Any]]
    extra_predicted_items: list[dict[str, Any]]
    matches: list[dict[str, Any]]


@dataclass(frozen=True)
class EvaluationReport:
    mode: str
    sample_count: int
    item_precision: float
    item_recall: float
    item_f1: float
    title_accuracy: float | None
    summary_accuracy: float | None
    type_accuracy: float | None
    datetime_accuracy: float | None
    date_status_accuracy: float | None
    title_similarity_avg: float | None
    summary_similarity_avg: float | None
    samples: list[SampleReport]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="라벨링된 가정통신문 JSON으로 /analyze 품질을 평가합니다."
    )
    parser.add_argument("dataset", help="라벨 JSON 파일 또는 JSON 파일 디렉터리")
    parser.add_argument(
        "--mode",
        choices=("baseline", "openai"),
        default="baseline",
        help=(
            "baseline은 비용 없이 rule-based 분석을 실행하고, "
            "openai는 실제 OpenAI 호출을 허용합니다."
        ),
    )
    parser.add_argument("--report-output", help="상세 평가 리포트를 저장할 JSON 경로")
    parser.add_argument(
        "--fail-under-f1",
        type=float,
        default=None,
        help="전체 item F1이 기준 미만이면 exit code 1을 반환합니다.",
    )
    args = parser.parse_args()

    if args.mode == "baseline":
        os.environ["OPENAI_ENABLED"] = "false"
    else:
        os.environ["OPENAI_ENABLED"] = "true"

    samples = load_samples(Path(args.dataset))
    report = evaluate_samples(samples, mode=args.mode)

    print_summary(report)
    if args.report_output:
        output_path = Path(args.report_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(asdict(report), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"상세 리포트 저장: {output_path}")

    if args.fail_under_f1 is not None and report.item_f1 < args.fail_under_f1:
        return 1
    return 0


def load_samples(dataset_path: Path) -> list[LabelSample]:
    if dataset_path.is_dir():
        raw_samples: list[dict[str, Any]] = []
        for path in sorted(dataset_path.glob("*.json")):
            raw_samples.extend(_read_sample_file(path))
    else:
        raw_samples = _read_sample_file(dataset_path)

    if not raw_samples:
        raise ValueError("평가할 라벨 JSON이 없습니다.")
    return [parse_sample(raw, index) for index, raw in enumerate(raw_samples, start=1)]


def _read_sample_file(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [_with_file_metadata(_ensure_mapping(item, path), path) for item in data]
    if isinstance(data, dict) and isinstance(data.get("samples"), list):
        return [_with_file_metadata(_ensure_mapping(item, path), path) for item in data["samples"]]
    if isinstance(data, dict):
        return [_with_file_metadata(data, path)]
    raise ValueError(f"{path}는 JSON object, object array, samples array 중 하나여야 합니다.")


def _ensure_mapping(value: Any, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path}의 sample은 JSON object여야 합니다.")
    return value


def _with_file_metadata(value: dict[str, Any], path: Path) -> dict[str, Any]:
    result = dict(value)
    result.setdefault("_fileStem", path.stem)
    result.setdefault("sourceFile", _find_partner_source_file(path))
    return result


def _find_partner_source_file(path: Path) -> str | None:
    for suffix in (".pdf", ".jpg", ".jpeg", ".png"):
        candidate = path.with_suffix(suffix)
        if candidate.exists():
            return candidate.name
    return None


def parse_sample(raw: dict[str, Any], index: int) -> LabelSample:
    if "labels" in raw:
        return parse_labeling_sample(raw, index)

    request_data = _first_mapping(raw, "input", "request")
    if request_data is None:
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
    request = NewsletterAnalysisRequest.model_validate(request_data)

    expected_data = _first_mapping(raw, "expected", "label", "labels") or raw
    expected_items_raw = expected_data.get("items", [])
    if not isinstance(expected_items_raw, list):
        raise ValueError("expected.items는 배열이어야 합니다.")

    return LabelSample(
        sample_id=str(
            raw.get("sampleId")
            or raw.get("id")
            or raw.get("_fileStem")
            or f"sample_{index}"
        ),
        source_file=_optional_str(raw.get("sourceFile")),
        request=request,
        expected_title=_optional_str(expected_data.get("title")),
        expected_summary=_optional_str(expected_data.get("summary")),
        expected_items=[parse_label_item(item) for item in expected_items_raw],
    )


def parse_labeling_sample(raw: dict[str, Any], index: int) -> LabelSample:
    original_text = _optional_str(raw.get("originalText") or raw.get("ocrText") or raw.get("text"))
    if original_text is None:
        original_text = _compose_text_from_labels(raw)

    request = NewsletterAnalysisRequest.model_validate(
        {
            "originalText": original_text,
            "translatedText": raw.get("translatedText"),
            "language": raw.get("language") or "KO",
            "referenceDate": raw.get("documentDate"),
            "timezone": raw.get("timezone") or "Asia/Seoul",
            "dateCandidates": [
                normalize_date_candidate(candidate, original_text, index)
                for index, candidate in enumerate(raw.get("dateCandidates") or [], start=1)
            ],
        }
    )

    labels = raw.get("labels")
    if not isinstance(labels, list):
        raise ValueError("labels는 배열이어야 합니다.")

    return LabelSample(
        sample_id=str(
            raw.get("sampleId")
            or raw.get("_fileStem")
            or raw.get("documentId")
            or f"sample_{index}"
        ),
        source_file=_optional_str(raw.get("sourceFile")),
        request=request,
        expected_title=_optional_str(raw.get("documentTitle")),
        expected_summary=_optional_str(raw.get("summary")),
        expected_items=[parse_label_item(item) for item in labels],
    )


def _compose_text_from_labels(raw: dict[str, Any]) -> str:
    parts = [
        _optional_str(raw.get("documentTitle")),
        _optional_str(raw.get("school")),
        _optional_str(raw.get("documentDate")),
    ]
    for item in raw.get("labels") or []:
        if isinstance(item, dict):
            parts.append(_optional_str(item.get("evidenceText")))

    # OCR 원문이 없는 라벨셋도 평가 스크립트에 태우기 위한 fallback입니다.
    # 실제 OCR 품질까지 보려면 originalText가 포함된 JSON으로 확장해야 합니다.
    return "\n".join(dict.fromkeys(part for part in parts if part))


def normalize_date_candidate(
    raw: dict[str, Any],
    source_text: str,
    index: int,
) -> dict[str, Any]:
    original_text = str(raw.get("originalText") or raw.get("raw") or raw.get("text") or "")
    normalized_date = _date_part(
        raw.get("normalizedDate") or raw.get("resolved") or raw.get("date") or date.today()
    )
    start_offset = raw.get("startOffset")
    end_offset = raw.get("endOffset")
    if start_offset is None or end_offset is None:
        found_at = source_text.find(original_text) if original_text else -1
        start_offset = max(found_at, 0)
        end_offset = start_offset + len(original_text)

    return {
        "candidateId": raw.get("candidateId") or raw.get("id") or f"dc_{index}",
        "originalText": original_text or str(normalized_date),
        "normalizedDate": normalized_date,
        "startOffset": start_offset,
        "endOffset": end_offset,
        "extractionType": raw.get("extractionType") or raw.get("type") or "LABEL",
    }


def parse_label_item(raw: Any) -> LabelItem:
    if not isinstance(raw, dict):
        raise ValueError("items 항목은 JSON object여야 합니다.")

    selected = raw.get("selectedDateCandidate")
    selected_id = None
    if isinstance(selected, dict):
        selected_id = _optional_str(selected.get("candidateId"))

    return LabelItem(
        type=str(raw.get("type") or ""),
        title=str(raw.get("title") or ""),
        date_status=str(raw.get("dateStatus") or raw.get("date_status") or ""),
        datetime=_optional_str(raw.get("datetime") or raw.get("date")),
        evidence_text=_optional_str(raw.get("evidenceText") or raw.get("evidence_text")),
        selected_date_candidate_id=_optional_str(raw.get("selectedDateCandidateId")) or selected_id,
    )


def evaluate_samples(samples: list[LabelSample], *, mode: str) -> EvaluationReport:
    reports = []
    for sample in samples:
        predicted = analyze_newsletter(sample.request)
        reports.append(evaluate_sample(sample, predicted))

    return EvaluationReport(
        mode=mode,
        sample_count=len(reports),
        item_precision=_avg([report.item_precision for report in reports]),
        item_recall=_avg([report.item_recall for report in reports]),
        item_f1=_avg([report.item_f1 for report in reports]),
        title_accuracy=_ratio([report.title_match for report in reports]),
        summary_accuracy=_ratio([report.summary_match for report in reports]),
        type_accuracy=_avg_optional([report.type_accuracy for report in reports]),
        datetime_accuracy=_avg_optional([report.datetime_accuracy for report in reports]),
        date_status_accuracy=_avg_optional([report.date_status_accuracy for report in reports]),
        title_similarity_avg=_avg_optional([report.title_similarity for report in reports]),
        summary_similarity_avg=_avg_optional([report.summary_similarity for report in reports]),
        samples=reports,
    )


def evaluate_sample(sample: LabelSample, predicted: NewsletterAnalysisResponse) -> SampleReport:
    predicted_items = [prediction_to_label_item(item) for item in predicted.items]
    matches = match_items(sample.expected_items, predicted_items)
    matched_expected = {match.expected_index for match in matches}
    matched_predicted = {match.predicted_index for match in matches}

    precision = (
        len(matches) / len(predicted_items)
        if predicted_items
        else float(not sample.expected_items)
    )
    recall = len(matches) / len(sample.expected_items) if sample.expected_items else 1.0
    f1 = _f1(precision, recall)

    return SampleReport(
        sample_id=sample.sample_id,
        title_match=_match_optional_text(sample.expected_title, predicted.title),
        title_similarity=_similarity_optional(sample.expected_title, predicted.title),
        summary_match=_match_optional_text(sample.expected_summary, predicted.summary),
        summary_similarity=_similarity_optional(sample.expected_summary, predicted.summary),
        expected_item_count=len(sample.expected_items),
        predicted_item_count=len(predicted_items),
        matched_item_count=len(matches),
        item_precision=precision,
        item_recall=recall,
        item_f1=f1,
        type_accuracy=_match_accuracy(matches, "type_match"),
        datetime_accuracy=_match_accuracy(matches, "datetime_match"),
        date_status_accuracy=_match_accuracy(matches, "date_status_match"),
        title_similarity_avg=_avg_optional([match.title_similarity for match in matches]),
        missing_expected_items=[
            asdict(item)
            for index, item in enumerate(sample.expected_items)
            if index not in matched_expected
        ],
        extra_predicted_items=[
            asdict(item)
            for index, item in enumerate(predicted_items)
            if index not in matched_predicted
        ],
        matches=[asdict(match) for match in matches],
    )


def prediction_to_label_item(item: Any) -> LabelItem:
    selected_id = None
    if item.selected_date_candidate is not None:
        selected_id = item.selected_date_candidate.candidate_id
    return LabelItem(
        type=str(item.type.value),
        title=item.title,
        date_status=str(item.date_status.value),
        datetime=item.datetime,
        evidence_text=item.evidence_text,
        selected_date_candidate_id=selected_id,
    )


def match_items(
    expected_items: list[LabelItem],
    predicted_items: list[LabelItem],
) -> list[ItemMatch]:
    candidates = []
    for expected_index, expected in enumerate(expected_items):
        for predicted_index, predicted in enumerate(predicted_items):
            score = score_item(expected, predicted)
            if score >= 0.55:
                candidates.append((score, expected_index, predicted_index))

    matches = []
    used_expected = set()
    used_predicted = set()
    for score, expected_index, predicted_index in sorted(candidates, reverse=True):
        if expected_index in used_expected or predicted_index in used_predicted:
            continue
        expected = expected_items[expected_index]
        predicted = predicted_items[predicted_index]
        matches.append(
            ItemMatch(
                expected_index=expected_index,
                predicted_index=predicted_index,
                score=round(score, 4),
                type_match=expected.type == predicted.type,
                title_similarity=round(_similarity(expected.title, predicted.title), 4),
                date_status_match=expected.date_status == predicted.date_status,
                datetime_match=_normalize_date(expected.datetime)
                == _normalize_date(predicted.datetime),
            )
        )
        used_expected.add(expected_index)
        used_predicted.add(predicted_index)
    return sorted(matches, key=lambda match: match.expected_index)


def score_item(expected: LabelItem, predicted: LabelItem) -> float:
    score = 0.0
    if expected.type == predicted.type:
        score += 0.35
    if expected.date_status == predicted.date_status:
        score += 0.15
    if _normalize_date(expected.datetime) == _normalize_date(predicted.datetime):
        score += 0.25
    score += _similarity(expected.title, predicted.title) * 0.25
    return score


def print_summary(report: EvaluationReport) -> None:
    print(f"mode: {report.mode}")
    print(f"samples: {report.sample_count}")
    print(
        "items: "
        f"precision={report.item_precision:.3f}, "
        f"recall={report.item_recall:.3f}, "
        f"f1={report.item_f1:.3f}"
    )
    print(f"title_accuracy: {_format_optional(report.title_accuracy)}")
    print(f"summary_accuracy: {_format_optional(report.summary_accuracy)}")
    print(f"type_accuracy: {_format_optional(report.type_accuracy)}")
    print(f"datetime_accuracy: {_format_optional(report.datetime_accuracy)}")
    print(f"date_status_accuracy: {_format_optional(report.date_status_accuracy)}")

    weak_samples = [sample for sample in report.samples if sample.item_f1 < 1.0]
    if weak_samples:
        print("mismatch samples:")
        for sample in weak_samples[:10]:
            print(
                f"- {sample.sample_id}: "
                f"expected={sample.expected_item_count}, "
                f"predicted={sample.predicted_item_count}, "
                f"matched={sample.matched_item_count}, "
                f"f1={sample.item_f1:.3f}"
            )


def _first_mapping(raw: dict[str, Any], *keys: str) -> dict[str, Any] | None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, dict):
            return value
    return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text != "" else None


def _date_part(value: Any) -> str:
    return str(value)[:10]


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", value).strip().casefold()
    return re.sub(r"[^\w가-힣]+", "", text)


def _normalize_date(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return value[:10]


def _similarity(left: str | None, right: str | None) -> float:
    return SequenceMatcher(None, _normalize_text(left), _normalize_text(right)).ratio()


def _match_optional_text(expected: str | None, predicted: str) -> bool | None:
    if expected is None:
        return None
    return _normalize_text(expected) == _normalize_text(predicted)


def _similarity_optional(expected: str | None, predicted: str) -> float | None:
    if expected is None:
        return None
    return _similarity(expected, predicted)


def _match_accuracy(matches: list[ItemMatch], field_name: str) -> float | None:
    if not matches:
        return None
    return sum(1 for match in matches if getattr(match, field_name)) / len(matches)


def _ratio(values: list[bool | None]) -> float | None:
    scoped = [value for value in values if value is not None]
    if not scoped:
        return None
    return sum(1 for value in scoped if value) / len(scoped)


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _avg_optional(values: list[float | None]) -> float | None:
    scoped = [value for value in values if value is not None]
    if not scoped:
        return None
    return sum(scoped) / len(scoped)


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _format_optional(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


if __name__ == "__main__":
    raise SystemExit(main())
