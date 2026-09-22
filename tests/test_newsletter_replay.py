import json

from test_openai_adapter import _valid_response

from app.schemas import NewsletterAnalysisResponse
from scripts.replay_newsletter_results import evaluate, replay


def test_evaluation_detects_missing_events_times_conditions_and_extra_actions():
    response = NewsletterAnalysisResponse.model_validate(_valid_response())
    checks = evaluate(
        response,
        {
            "typedDates": [["deadline", "2026-06-15"]],
            "requiredTimes": [["2026-06-15", "09:00"]],
            "requiredDetailPatterns": ["선착순"],
            "forbiddenActionPatterns": ["수영복"],
        },
    )
    assert checks["summaryPresent"] is True
    assert not any(value for key, value in checks.items() if key != "summaryPresent")


def test_replay_counts_missing_and_invalid_responses_as_failures(tmp_path):
    for case_id in ("missing", "invalid"):
        (tmp_path / f"{case_id}-input.json").write_text(
            json.dumps(
                {
                    "request": {"originalText": "일반 안내"},
                    "expected": {"emptyItems": True},
                }
            ),
            encoding="utf-8",
        )
    (tmp_path / "invalid-run-1-draft-raw.json").write_text('{"items": ["},{"]}', encoding="utf-8")
    rows = replay(tmp_path, "draft")
    assert len(rows) == 2
    assert not any(row["passed"] for row in rows)
    assert {row["error"] for row in rows} == {"MISSING_RESPONSE", "INVALID_RESPONSE"}


def test_empty_directory_does_not_report_passed_cases(tmp_path):
    assert replay(tmp_path, "draft") == []
