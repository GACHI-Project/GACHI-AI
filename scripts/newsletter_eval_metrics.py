"""Deterministic graders; similarity is diagnostic, not semantic correctness."""

from __future__ import annotations

import re
from dataclasses import asdict
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.schemas import NewsletterAnalysisResponse
from scripts.newsletter_eval_data import LabelItem, LabelSample, parse_label_item


def normalize_text(value: str | None) -> str:
    return re.sub(r"[^\w가-힣]", "", (value or "").casefold())


def similarity(left: str | None, right: str | None) -> float:
    return SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def temporal(value: str | None, timezone: str = "Asia/Seoul") -> tuple | None:
    if value is None:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return ("date", date.fromisoformat(value))
    if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", value):
        raise ValueError("INVALID_DATETIME_FORMAT")
    parsed = datetime.fromisoformat(value)
    parsed = parsed.replace(tzinfo=ZoneInfo(timezone)) if parsed.tzinfo is None else parsed
    return ("datetime", parsed.astimezone(ZoneInfo("UTC")))


def temporal_equal(
    left: str | None,
    right: str | None,
    left_zone: str = "Asia/Seoul",
    right_zone: str = "Asia/Seoul",
) -> bool:
    try:
        return temporal(left, left_zone) == temporal(right, right_zone)
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        return False


def local_part(
    value: str | None, timezone: str, *, time_only: bool = False, target_zone: str | None = None
) -> Any:
    parsed = temporal(value, timezone)
    if parsed is None:
        return None
    if parsed[0] == "date":
        return None if time_only else parsed[1]
    localized = parsed[1].astimezone(ZoneInfo(target_zone or timezone))
    return localized.timetz().replace(tzinfo=None) if time_only else localized.date()


def part_equal(expected: LabelItem, predicted: LabelItem, *, time_only: bool) -> bool:
    try:
        return local_part(expected.datetime, expected.timezone, time_only=time_only) == local_part(
            predicted.datetime,
            predicted.timezone,
            time_only=time_only,
            target_zone=expected.timezone,
        )
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        return False


def match_items(expected: list[LabelItem], predicted: list[LabelItem]) -> list[tuple[int, int]]:
    # Event identity is primarily its title: wrong dates/statuses must remain gradeable.
    candidates = []
    for ei, gold in enumerate(expected):
        for pi, actual in enumerate(predicted):
            score = (
                0.75 * similarity(gold.title, actual.title)
                + 0.15 * (gold.type == actual.type)
                + 0.10
                * temporal_equal(gold.datetime, actual.datetime, gold.timezone, actual.timezone)
            )
            if score >= 0.55:
                candidates.append((score, ei, pi))
    matched = []
    used_expected, used_predicted = set(), set()
    for _, ei, pi in sorted(candidates, key=lambda row: (-row[0], row[1], row[2])):
        if ei not in used_expected and pi not in used_predicted:
            matched.append((ei, pi))
            used_expected.add(ei)
            used_predicted.add(pi)
    return sorted(matched)


def action_matches(expected: dict, predicted: dict) -> bool:
    if expected.get("contentPatterns"):
        return all(
            re.search(pattern, predicted["content"]) for pattern in expected["contentPatterns"]
        )
    accepted = [expected["content"], *expected.get("acceptedContents", [])]
    return normalize_text(predicted["content"]) in {normalize_text(text) for text in accepted}


def detail_matches(expected: dict, predicted: dict) -> bool | None:
    if expected.get("detailPatterns"):
        return all(
            re.search(pattern, predicted.get("detail") or "")
            for pattern in expected["detailPatterns"]
        )
    if expected.get("detail") is None:
        return None
    return normalize_text(expected["detail"]) == normalize_text(predicted.get("detail"))


def grade_checklists(
    expected: list[LabelItem], predicted: list[LabelItem], pairs: list[tuple[int, int]]
) -> dict[str, Any]:
    scored = {index for index, item in enumerate(expected) if item.checklist_items is not None}
    if not expected:
        extra = [
            {"itemIndex": i, "content": action["content"]}
            for i, item in enumerate(predicted)
            for action in (item.checklist_items or [])
        ]
        return {
            "checklist_precision": float(not extra),
            "checklist_recall": 1.0,
            "checklist_f1": float(not extra),
            "checklist_detail_accuracy": None,
            "checklist_missing": [],
            "checklist_extra": extra,
            "checklist_duplicates": [],
            "checklist_scored_item_count": 0,
        }
    if not scored:
        return {
            "checklist_precision": None,
            "checklist_recall": None,
            "checklist_f1": None,
            "checklist_detail_accuracy": None,
            "checklist_missing": [],
            "checklist_extra": [],
            "checklist_duplicates": [],
            "checklist_scored_item_count": 0,
        }
    paired = dict(pairs)
    missing, extra, duplicate, detail_results = [], [], [], []
    matched_count = 0
    predicted_count = 0
    expected_count = sum(len(expected[i].checklist_items or []) for i in scored)
    for ei in sorted(scored):
        gold = expected[ei].checklist_items or []
        pi = paired.get(ei)
        actual = (predicted[pi].checklist_items or []) if pi is not None else []
        predicted_count += len(actual)
        used, seen = set(), set()
        for action in actual:
            key = normalize_text(action["content"])
            if key in seen:
                duplicate.append({"itemIndex": pi, "content": action["content"]})
            seen.add(key)
        for action in gold:
            match = next(
                (
                    ai
                    for ai, value in enumerate(actual)
                    if ai not in used and action_matches(action, value)
                ),
                None,
            )
            if match is None:
                missing.append({"itemIndex": ei, "content": action["content"]})
            else:
                used.add(match)
                matched_count += 1
                detail_results.append(detail_matches(action, actual[match]))
        extra.extend(
            {"itemIndex": pi, "content": value["content"]}
            for ai, value in enumerate(actual)
            if ai not in used
        )
    if len(scored) == len(expected):
        matched_predicted = {pi for _, pi in pairs}
        for pi, item in enumerate(predicted):
            if pi not in matched_predicted:
                actions = item.checklist_items or []
                predicted_count += len(actions)
                extra.extend({"itemIndex": pi, "content": value["content"]} for value in actions)
    precision = matched_count / predicted_count if predicted_count else float(expected_count == 0)
    recall = matched_count / expected_count if expected_count else 1.0
    cross_item_seen = {}
    for pi, item in enumerate(predicted):
        for action in item.checklist_items or []:
            key = (normalize_text(action["content"]), normalize_text(action.get("detail")))
            if key in cross_item_seen and cross_item_seen[key] != pi:
                duplicate.append(
                    {
                        "itemIndex": pi,
                        "content": action["content"],
                        "otherItemIndex": cross_item_seen[key],
                    }
                )
            cross_item_seen[key] = pi
    return {
        "checklist_precision": precision,
        "checklist_recall": recall,
        "checklist_f1": f1(precision, recall),
        "checklist_detail_accuracy": mean_optional(detail_results),
        "checklist_missing": missing,
        "checklist_extra": extra,
        "checklist_duplicates": duplicate,
        "checklist_scored_item_count": len(scored),
    }


def evaluate_sample(sample: LabelSample, response: NewsletterAnalysisResponse) -> dict[str, Any]:
    predicted = [
        parse_label_item(item.model_dump(by_alias=True), validate=False) for item in response.items
    ]
    expected = sample.expected_items
    pairs = match_items(expected, predicted)
    expected_indices, predicted_indices = {e for e, _ in pairs}, {p for _, p in pairs}
    matches = []
    for ei, pi in pairs:
        gold, actual = expected[ei], predicted[pi]
        matches.append(
            {
                "expected_index": ei,
                "predicted_index": pi,
                "title_similarity": similarity(gold.title, actual.title),
                "type_match": gold.type == actual.type,
                "datetime_match": temporal_equal(
                    gold.datetime, actual.datetime, gold.timezone, actual.timezone
                ),
                "date_match": part_equal(gold, actual, time_only=False),
                "time_match": part_equal(gold, actual, time_only=True),
                "end_datetime_match": temporal_equal(
                    gold.end_datetime, actual.end_datetime, gold.timezone, actual.timezone
                ),
                "period_start_datetime_match": temporal_equal(
                    gold.period_start_datetime,
                    actual.period_start_datetime,
                    gold.timezone,
                    actual.timezone,
                ),
                "date_status_match": gold.date_status == actual.date_status,
                "needs_user_confirmation_match": (
                    gold.needs_user_confirmation == actual.needs_user_confirmation
                ),
            }
        )
    precision = len(pairs) / len(predicted) if predicted else float(not expected)
    recall = len(pairs) / len(expected) if expected else 1.0
    report = {
        "sample_id": sample.sample_id,
        "error": None,
        "title_match": optional_text_equal(sample.expected_title, response.title),
        "summary_match": optional_text_equal(sample.expected_summary, response.summary),
        "title_similarity": None
        if sample.expected_title is None
        else similarity(sample.expected_title, response.title),
        "summary_similarity": None
        if sample.expected_summary is None
        else similarity(sample.expected_summary, response.summary),
        "expected_item_count": len(expected),
        "predicted_item_count": len(predicted),
        "matched_item_count": len(pairs),
        "item_precision": precision,
        "item_recall": recall,
        "item_f1": f1(precision, recall),
        "matches": matches,
        "missing_expected_items": [
            asdict(value) for i, value in enumerate(expected) if i not in expected_indices
        ],
        "extra_predicted_items": [
            asdict(value) for i, value in enumerate(predicted) if i not in predicted_indices
        ],
        "manual_review_required": True,
    }
    for key in (
        "type",
        "datetime",
        "date",
        "time",
        "end_datetime",
        "period_start_datetime",
        "date_status",
        "needs_user_confirmation",
    ):
        report[f"{key}_accuracy"] = mean_optional([match[f"{key}_match"] for match in matches])
    report.update(grade_checklists(expected, predicted, pairs))
    return report


def optional_text_equal(expected: str | None, actual: str) -> bool | None:
    return None if expected is None else normalize_text(expected) == normalize_text(actual)


def mean_optional(values: list) -> float | None:
    selected = [value for value in values if value is not None]
    return sum(selected) / len(selected) if selected else None


def f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0
