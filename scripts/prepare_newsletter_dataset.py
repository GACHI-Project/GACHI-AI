"""Migrate labels and merge BE OCR JSONs by sampleId. Does not call external APIs."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.newsletter_eval_data import (  # noqa: E402
    SCHEMA_VERSION,
    merge_be_result,
    parse_label_item,
    parse_sample,
    read_records,
)


def migrate_sample(raw: dict) -> dict:
    result = {key: copy.deepcopy(value) for key, value in raw.items() if not key.startswith("_")}
    result["sampleId"] = str(raw.get("sampleId") or raw.get("documentId") or raw.get("_fileStem"))
    expected = result.get("expected")
    if expected is None and isinstance(result.get("labels"), list):
        expected = {
            "title": result.get("documentTitle"),
            "summary": result.get("summary"),
            "items": result["labels"],
        }
    if not isinstance(expected, dict) or not isinstance(expected.get("items"), list):
        raise ValueError("MISSING_EXPECTED_ITEMS")
    notes = list(result.get("metadata", {}).get("reviewNotes", []))
    for item in expected["items"]:
        item["datetime"] = item.get("datetime", item.pop("date", None))
        value = item["datetime"]
        if value and ("T00:00:00" in value or "T23:59:59" in value):
            clock = value.split("T", 1)[1][:8]
            if clock not in (item.get("evidenceText") or ""):
                item["datetime"] = value[:10]
                notes.append(f"{item['title']}: 근거 없는 기본 시각 제거")
        for key in ("endDatetime", "periodStartDatetime"):
            item.setdefault(key, None)
        item.setdefault("timezone", "Asia/Seoul")
        item.setdefault("needsUserConfirmation", item.get("dateStatus") == "ambiguous")
        if item.get("dateStatus") != "confirmed":
            item.update(datetime=None, endDatetime=None, periodStartDatetime=None)
        if item.get("type") == "reminder":
            item.update(
                dateStatus="missing",
                datetime=None,
                needsUserConfirmation=False,
                endDatetime=None,
                periodStartDatetime=None,
            )
        item.pop("confidence", None)  # Human certainty is not the model confidence target.
        # Bind candidate IDs only after importing actual BE candidates, not manual draft candidates.
        item.pop("selectedDateCandidate", None)
        item.pop("selectedDateCandidateId", None)
    old_candidates = result.pop("dateCandidates", [])
    if old_candidates:
        result["legacyDateCandidates"] = old_candidates
    actual_input = result.get("input")
    if not actual_input and isinstance(result.get("originalText"), str):
        # Still validated at merge/evaluation; never use labels to build this input.
        actual_input = {
            key: result[key]
            for key in ("originalText", "translatedText", "referenceDate", "language", "timezone")
            if key in result
        }
        actual_input["dateCandidates"] = old_candidates
    for key in ("labels", "originalText", "translatedText", "inputStatus"):
        result.pop(key, None)
    result.update(
        schemaVersion=SCHEMA_VERSION,
        input=actual_input,
        expected=expected,
        offsetEncoding="codepoint",
    )
    result["metadata"] = {
        **result.get("metadata", {}),
        "annotationStatus": "draft",
        "labelVersion": "3-draft",
        "inputStatus": "ready" if actual_input else "pending_actual_ocr",
        "reviewNotes": list(
            dict.fromkeys(
                [*notes, "원본에서 시간/기간, 연도 충돌, 조건부 행동을 검수한 뒤 reviewed로 변경"]
            )
        ),
    }
    return result


def prepare(labels: Path, output: Path, ocr_results: Path | None = None) -> list[dict]:
    raw_samples = read_records(labels)
    samples = []
    used_ids = set()
    for raw in raw_samples:
        sample = (
            migrate_sample(raw)
            if raw.get("schemaVersion") != SCHEMA_VERSION
            else {key: value for key, value in raw.items() if not key.startswith("_")}
        )
        sample_id = sample["sampleId"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", sample_id):
            raise ValueError("INVALID_SAMPLE_ID")
        if sample_id in used_ids:
            raise ValueError("DUPLICATE_SAMPLE_ID")
        used_ids.add(sample_id)
        if ocr_results is not None:
            result_file = ocr_results / f"{sample_id}.json"
            be_result = json.loads(result_file.read_text(encoding="utf-8-sig"))
            sample = merge_be_result(sample, be_result)
            # Relative source paths in a BE export are relative to that export, not the label file.
            for source in sample["sourceFiles"]:
                source["path"] = str((result_file.parent / source["path"]).resolve())
            expected = sample["expected"]
            for item in expected["items"]:
                item.pop("selectedDateCandidate", None)
                matching = [
                    candidate
                    for candidate in sample["input"]["dateCandidates"]
                    if item.get("datetime") and candidate["normalizedDate"] == item["datetime"][:10]
                ]
                item["selectedDateCandidateId"] = (
                    matching[0]["candidateId"] if len(matching) == 1 else None
                )
            parse_sample(sample, allow_drafts=True)
        for item in sample["expected"]["items"]:
            parse_label_item(item)
        for source in sample.get("sourceFiles", []):
            source["path"] = str((Path(raw["_baseDir"]) / source["path"]).resolve())
        samples.append(sample)
    # All records pass preflight before any output is written. Do not overwrite source gold files.
    if output.resolve() == labels.resolve():
        raise ValueError("OUTPUT_MUST_DIFFER_FROM_SOURCE")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(
            {"schemaVersion": SCHEMA_VERSION, "samples": samples},
            stream,
            ensure_ascii=False,
            indent=2,
        )
        stream.write("\n")
    return samples


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels", type=Path)
    parser.add_argument("--ocr-results", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        samples = prepare(args.labels, args.output, args.ocr_results)
    except (ValueError, OSError, KeyError):
        print("준비 실패: 입력 상태, sampleId, BE 결과 및 출력 경로를 확인하세요.", file=sys.stderr)
        return 2
    print(f"Prepared={len(samples)}; output={args.output}; no API calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
