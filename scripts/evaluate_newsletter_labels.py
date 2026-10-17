"""Evaluate actual OCR inputs, never synthesized gold evidence. Paid calls are opt-in."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import get_openai_settings  # noqa: E402
from app.services.newsletter_extractor import analyze_newsletter  # noqa: E402
from scripts.newsletter_eval_data import (
    EvaluationInputError,
    LabelItem,
    LabelSample,
    load_local_documents,
    load_samples,
    parse_label_item,
    parse_sample,
)
from scripts.newsletter_eval_metrics import evaluate_sample, match_items, mean_optional

__all__ = [
    "LabelItem",
    "LabelSample",
    "load_samples",
    "parse_sample",
    "parse_label_item",
    "evaluate_sample",
    "match_items",
    "evaluate_samples",
    "main",
]


def reproducibility(samples: list[LabelSample], mode: str, with_documents: bool) -> dict:
    def git(*args):
        result = subprocess.run(
            ["git", *args], cwd=ROOT_DIR, capture_output=True, text=True, check=False
        )
        return result.stdout.strip() if result.returncode == 0 else "unavailable"

    settings = get_openai_settings()
    return {
        "evaluatorVersion": "3",
        "generatedAt": datetime.now(UTC).isoformat(),
        "codeCommit": git("rev-parse", "HEAD"),
        "workingTreeStatus": git("status", "--porcelain"),
        "model": settings.model if mode == "openai" else None,
        "withDocuments": with_documents,
        "documentDetail": settings.document_detail if with_documents else None,
        "promptSha256": hashlib.sha256(
            (ROOT_DIR / "app/services/newsletter_prompt.py").read_bytes()
        ).hexdigest(),
        "evaluatorSha256": hashlib.sha256(
            b"".join(
                (ROOT_DIR / f"scripts/{name}.py").read_bytes()
                for name in (
                    "evaluate_newsletter_labels",
                    "newsletter_eval_data",
                    "newsletter_eval_metrics",
                )
            )
        ).hexdigest(),
        "datasets": [
            {
                "sampleId": sample.sample_id,
                "sha256": sample.dataset_sha256,
                "referenceDate": str(sample.request.reference_date),
                "annotation": sample.metadata,
                "sourceSha256": [source.get("sha256") for source in sample.source_files],
            }
            for sample in samples
        ],
        "unscoredFields": ["confidence", "translations", "conversationTopics", "meta"],
    }


def evaluate_samples(
    samples: list[LabelSample],
    *,
    mode: str,
    with_documents: bool = False,
    delay_seconds: float = 0,
) -> dict:
    if not samples:
        raise ValueError("EMPTY_DATASET")
    if mode not in {"baseline", "openai"}:
        raise ValueError("INVALID_MODE")
    if with_documents and mode != "openai":
        raise ValueError("DOCUMENTS_REQUIRE_OPENAI_MODE")
    if not math.isfinite(delay_seconds) or delay_seconds < 0:
        raise ValueError("INVALID_DELAY_SECONDS")
    settings = get_openai_settings()
    documents = (
        {
            sample.sample_id: load_local_documents(sample, max_bytes=settings.document_max_bytes)
            for sample in samples
        }
        if with_documents
        else {}
    )
    previous = os.environ.get("OPENAI_ENABLED")
    os.environ["OPENAI_ENABLED"] = "true" if mode == "openai" else "false"
    rows = []
    try:
        for index, sample in enumerate(samples):
            if index and mode == "openai" and delay_seconds:
                time.sleep(delay_seconds)
            print(f"Analyzing {sample.sample_id} ({index + 1}/{len(samples)}) ...", flush=True)
            try:
                response = analyze_newsletter(
                    sample.request, documents=documents.get(sample.sample_id)
                )
                attached = response.meta.get("attachedDocumentCount", 0)
                if with_documents and attached != len(documents[sample.sample_id]):
                    raise ValueError("DOCUMENT_ATTACHMENT_FAILED")
                row = evaluate_sample(sample, response)
                row.update(
                    requested_document_count=len(documents.get(sample.sample_id, [])),
                    attached_document_count=attached,
                    prediction=response.model_dump(mode="json", by_alias=True, exclude={"meta"}),
                    document_sha256=[
                        hashlib.sha256(doc.content).hexdigest()
                        for doc in documents.get(sample.sample_id, [])
                    ],
                )
            except Exception as exc:
                row = {
                    "sample_id": sample.sample_id,
                    "error": (
                        "DOCUMENT_ATTACHMENT_FAILED"
                        if str(exc) == "DOCUMENT_ATTACHMENT_FAILED"
                        else "ANALYSIS_FAILED"
                    ),
                    "error_type": type(exc).__name__,
                    "item_precision": 0.0,
                    "item_recall": 0.0,
                    "item_f1": 0.0,
                }
            rows.append(row)
    finally:
        if previous is None:
            os.environ.pop("OPENAI_ENABLED", None)
        else:
            os.environ["OPENAI_ENABLED"] = previous
    report = {
        "mode": mode,
        "sample_count": len(samples),
        "failed_sample_count": sum(bool(row["error"]) for row in rows),
        "samples": rows,
        "reproducibility": reproducibility(samples, mode, with_documents),
        "delay_seconds": delay_seconds,
    }
    metrics = (
        "item_precision",
        "item_recall",
        "item_f1",
        "type_accuracy",
        "date_accuracy",
        "time_accuracy",
        "datetime_accuracy",
        "end_datetime_accuracy",
        "period_start_datetime_accuracy",
        "date_status_accuracy",
        "needs_user_confirmation_accuracy",
        "checklist_precision",
        "checklist_recall",
        "checklist_f1",
        "checklist_detail_accuracy",
    )
    for metric in metrics:
        report[metric] = mean_optional([row.get(metric) for row in rows])
    report["title_accuracy"] = mean_optional([row.get("title_match") for row in rows])
    report["summary_accuracy"] = mean_optional([row.get("summary_match") for row in rows])
    report["metric_sample_counts"] = {
        metric: sum(row.get(metric) is not None for row in rows) for metric in metrics
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--mode", choices=("baseline", "openai"), default="baseline")
    parser.add_argument("--with-documents", action="store_true")
    parser.add_argument("--allow-drafts", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--report-output", type=Path)
    parser.add_argument("--fail-under-f1", type=float)
    parser.add_argument("--delay-seconds", type=float, default=0)
    args = parser.parse_args(argv)
    try:
        if args.fail_under_f1 is not None and not 0 <= args.fail_under_f1 <= 1:
            raise ValueError("INVALID_F1_THRESHOLD")
        if not math.isfinite(args.delay_seconds) or args.delay_seconds < 0:
            raise ValueError("INVALID_DELAY_SECONDS")
        samples = load_samples(args.dataset, allow_drafts=args.allow_drafts)
        if args.with_documents and args.mode != "openai":
            raise ValueError("DOCUMENTS_REQUIRE_OPENAI_MODE")
        if args.validate_only:
            if args.with_documents:
                for sample in samples:
                    load_local_documents(sample, max_bytes=get_openai_settings().document_max_bytes)
            print(f"Validated samples={len(samples)}; no API calls")
            return 0
        report = evaluate_samples(
            samples,
            mode=args.mode,
            with_documents=args.with_documents,
            delay_seconds=args.delay_seconds,
        )
    except EvaluationInputError as exc:
        print(f"입력 검증 실패: {exc}", file=sys.stderr)
        return 2
    except (ValueError, OSError, KeyError):
        print(
            "입력 검증 실패: 실제 OCR, 기준일, 후보 위치, 정답 상태 및 원본 파일을 확인하세요.",
            file=sys.stderr,
        )
        return 2
    print(f"mode={args.mode}; samples={len(samples)}; failed={report['failed_sample_count']}")
    print(f"item_f1={report['item_f1']:.3f}; datetime_accuracy={report['datetime_accuracy']}")
    if args.report_output:
        args.report_output.parent.mkdir(parents=True, exist_ok=True)
        args.report_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Report: {args.report_output}")
    return int(
        bool(report["failed_sample_count"])
        or (args.fail_under_f1 is not None and report["item_f1"] < args.fail_under_f1)
    )


if __name__ == "__main__":
    raise SystemExit(main())
