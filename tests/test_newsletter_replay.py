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


def test_document_attached_replay_preserves_document_only_date(tmp_path):
    (tmp_path / "source-input.json").write_text(
        json.dumps(
            {
                "request": {"originalText": "2026. 6. 15 수영 실기교육 안내"},
                "expected": {"typedDates": [["schedule", "2026-06-15"]]},
            }
        ),
        encoding="utf-8",
    )
    raw = _valid_response()
    raw["items"][0]["selectedDateCandidate"] = None
    (tmp_path / "source-run-1-draft-raw.json").write_text(
        json.dumps(raw, ensure_ascii=False), encoding="utf-8"
    )

    text_only = replay(tmp_path, "draft")
    with_document = replay(tmp_path, "draft", documents_attached=True)

    assert not text_only[0]["passed"]
    assert text_only[0]["warnings"][0]["code"] == "DATE_CANDIDATE_MISMATCH"
    assert with_document[0]["passed"]
    assert with_document[0]["warnings"][0]["code"] == "DOCUMENT_ONLY_DATE"
