import json
from pathlib import Path

import pytest

from app.schemas import NewsletterAnalysisResponse
from scripts import evaluate_newsletter_labels as evaluator
from scripts.newsletter_eval_data import (
    SCHEMA_VERSION,
    load_local_documents,
    load_samples,
    merge_be_result,
    parse_sample,
    sha256,
)
from scripts.newsletter_eval_metrics import evaluate_sample, temporal_equal
from scripts.prepare_newsletter_dataset import migrate_sample, prepare


def gold_item(**changes):
    return {
        "type": "deadline",
        "title": "신청서 제출",
        "dateStatus": "confirmed",
        "datetime": "2026-09-28T18:00:00",
        "endDatetime": None,
        "periodStartDatetime": "2026-09-10T10:00:00",
        "timezone": "Asia/Seoul",
        "needsUserConfirmation": False,
        "evidenceText": "신청서를 제출하세요",
        "checklistItems": [{"content": "신청서 작성", "detailPatterns": ["서명"]}],
        **changes,
    }


def record(item=None, **changes):
    return {
        "schemaVersion": SCHEMA_VERSION,
        "sampleId": "pilot_001",
        "input": {
            "originalText": "9월 28일까지 신청서 제출",
            "referenceDate": "2026-10-18",
            "dateCandidates": [
                {
                    "candidateId": "dc_1",
                    "originalText": "9월 28일",
                    "normalizedDate": "2026-09-28",
                    "startOffset": 0,
                    "endOffset": 6,
                    "extractionType": "REGEX",
                }
            ],
        },
        "expected": {"title": "안내", "summary": "신청 안내", "items": [item or gold_item()]},
        "metadata": {"annotationStatus": "reviewed", "labelVersion": "3"},
        **changes,
    }


def response(item=None, **changes):
    value = gold_item() if item is None else item
    return NewsletterAnalysisResponse.model_validate(
        {
            "title": "안내",
            "summary": "신청 안내",
            "items": [{"confidence": 0.6, "confirmationQuestion": None, **value}],
            **changes,
        }
    )


def be_result():
    raw = record()
    return {
        "schemaVersion": "gachi-newsletter-ocr-v1",
        "processingVersion": "1",
        "sampleId": "pilot_001",
        "status": "SUCCESS",
        "input": raw["input"],
        "sourceFiles": [],
        "fingerprint": "hash",
    }


@pytest.mark.parametrize("value", [None, "", "  "])
def test_does_not_synthesize_ocr_from_gold_evidence(value):
    raw = record()
    raw["input"]["originalText"] = value
    with pytest.raises(ValueError, match="MISSING_OCR_TEXT"):
        parse_sample(raw)


def test_missing_reference_date_is_not_replaced_by_document_date():
    raw = record(documentDate="2023-03-02")
    raw["input"].pop("referenceDate")
    with pytest.raises(ValueError, match="MISSING_REFERENCE_DATE"):
        parse_sample(raw)


@pytest.mark.parametrize(
    "change",
    [{"startOffset": 1}, {"endOffset": 900}, {"candidateId": None}, {"normalizedDate": "invalid"}],
)
def test_invalid_candidate_inputs_rejected(change):
    raw = record()
    raw["input"]["dateCandidates"][0].update(change)
    with pytest.raises(ValueError):
        parse_sample(raw)


def test_be_utf16_offsets_are_converted_and_verified_after_emoji():
    value = be_result()
    value["input"]["originalText"] = "😀9월 28일까지 신청서 제출"
    value["input"]["dateCandidates"][0].update(startOffset=2, endOffset=8)
    merged = merge_be_result(record(), value)
    sample = parse_sample(merged)
    candidate = sample.request.date_candidates[0]
    assert candidate.start_offset == 1
    assert sample.request.original_text[candidate.start_offset : candidate.end_offset] == "9월 28일"


@pytest.mark.parametrize("status", ["PARTIAL", "FAILED"])
def test_incomplete_be_results_are_not_normal_evaluation_inputs(status):
    value = be_result()
    value["status"] = status
    with pytest.raises(ValueError, match="BE_OCR_NOT_SUCCESS"):
        merge_be_result(record(), value)


def test_import_rejects_wrong_id_and_schema():
    for changes in ({"sampleId": "other"}, {"schemaVersion": "v999"}):
        with pytest.raises(ValueError):
            merge_be_result(record(), {**be_result(), **changes})


def test_drafts_are_explicit_and_empty_expected_is_valid():
    raw = record(metadata={"annotationStatus": "draft"}, expected={"items": []})
    with pytest.raises(ValueError, match="UNREVIEWED_LABEL"):
        parse_sample(raw)
    assert parse_sample(raw, allow_drafts=True).expected_items == []
    raw.pop("expected")
    with pytest.raises(ValueError, match="MISSING_EXPECTED_ITEMS"):
        parse_sample(raw, allow_drafts=True)


@pytest.mark.parametrize("actual", ["2026-09-28T17:00:00", "2026-09-28", None])
def test_datetime_grader_detects_wrong_or_missing_time(actual):
    result = evaluate_sample(parse_sample(record()), response(gold_item(datetime=actual)))
    assert result["matched_item_count"] == 1
    assert result["datetime_accuracy"] == 0
    assert result["time_accuracy"] == 0


def test_invented_midnight_is_not_equal_to_date_only():
    expected = record(gold_item(datetime="2026-09-28", periodStartDatetime=None))
    result = evaluate_sample(
        parse_sample(expected),
        response(gold_item(datetime="2026-09-28T00:00:00+09:00", periodStartDatetime=None)),
    )
    assert result["date_accuracy"] == 1
    assert result["datetime_accuracy"] == 0
    assert result["time_accuracy"] == 0


def test_timezone_equivalence_and_invalid_datetime():
    assert temporal_equal("2026-09-28T18:00:00+09:00", "2026-09-28T09:00:00Z")
    assert not temporal_equal("2026-09-28", "2026-09-28T00:00:00")
    assert not temporal_equal("bad", "bad")


def test_timezone_is_applied_consistently_to_date_and_time_subscores():
    result = evaluate_sample(
        parse_sample(record()),
        response(
            gold_item(
                datetime="2026-09-28T09:00:00",
                timezone="UTC",
                periodStartDatetime="2026-09-10T01:00:00",
            )
        ),
    )
    assert result["datetime_accuracy"] == 1
    assert result["date_accuracy"] == 1
    assert result["time_accuracy"] == 1


def test_empty_gold_reports_extra_checklist_actions():
    sample = parse_sample(record(expected={"items": []}))
    result = evaluate_sample(
        sample, response(gold_item(checklistItems=[{"content": "원문에 없는 추가 행동"}]))
    )
    assert result["item_precision"] == 0
    assert result["checklist_precision"] == 0
    assert len(result["checklist_extra"]) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"endDatetime": "2026-09-28T17:00:00", "type": "schedule", "periodStartDatetime": None},
        {"periodStartDatetime": "2026-09-29T18:00:00"},
        {"checklistItems": [{"content": "제출", "contentPatterns": ["["]}]},
        {"checklistItems": [{"content": "제출", "contentPatterns": [""]}]},
    ],
)
def test_invalid_order_and_patterns_rejected_before_calls(changes):
    with pytest.raises(ValueError):
        parse_sample(record(gold_item(**changes)))


def test_reviewed_pilot_keeps_actual_ocr_separate_and_has_current_temporal_contract():
    path = Path(__file__).resolve().parents[1] / "data/newsletter-pilot/pilot-labels-v3.json"
    samples = json.loads(path.read_text(encoding="utf-8"))["samples"]
    assert len(samples) == 10
    assert all(sample["input"] is None for sample in samples)
    assert all(sample["metadata"]["annotationStatus"] == "reviewed" for sample in samples)
    sports = samples[2]["expected"]["items"]
    assert sports[0]["endDatetime"] == "2025-09-23T12:10:00+09:00"
    assert samples[6]["expected"]["items"][0]["periodStartDatetime"] == "2026-07-10"
    for sample in samples:
        for item in sample["expected"]["items"]:
            assert "T00:00:00" not in (item["datetime"] or "")
            assert "T23:59:59" not in (item["datetime"] or "")


def test_period_and_confirmation_errors_are_graded_separately():
    result = evaluate_sample(
        parse_sample(record()),
        response(gold_item(periodStartDatetime=None, needsUserConfirmation=True)),
    )
    assert result["period_start_datetime_accuracy"] == 0
    assert result["needs_user_confirmation_accuracy"] == 0
    schedule = gold_item(
        type="schedule", periodStartDatetime=None, endDatetime="2026-09-28T20:00:00"
    )
    result = evaluate_sample(
        parse_sample(record(schedule)), response({**schedule, "endDatetime": "2026-09-28T19:00:00"})
    )
    assert result["end_datetime_accuracy"] == 0


def test_checklist_missing_extra_duplicate_and_detail_failures():
    expected = gold_item(
        checklistItems=[
            {"content": "신청서 작성", "detailPatterns": ["서명"]},
            {"content": "신청서 제출"},
        ]
    )
    actual = gold_item(
        checklistItems=[
            {"content": "신청서 작성", "detail": "온라인"},
            {"content": "신청서 작성"},
            {"content": "수영복 준비"},
        ]
    )
    result = evaluate_sample(parse_sample(record(expected)), response(actual))
    assert result["checklist_recall"] == 0.5
    assert result["checklist_precision"] == pytest.approx(1 / 3)
    assert result["checklist_detail_accuracy"] == 0
    assert len(result["checklist_missing"]) == 1
    assert len(result["checklist_extra"]) == 2
    assert len(result["checklist_duplicates"]) == 1


def test_checklist_unannotated_is_not_scored_as_empty():
    expected = gold_item()
    expected.pop("checklistItems")
    result = evaluate_sample(parse_sample(record(expected)), response())
    assert result["checklist_f1"] is None


def test_patterns_can_accept_wording_without_implicit_semantic_grading():
    expected = gold_item(
        checklistItems=[{"content": "동의서 제출", "contentPatterns": ["동의서", "제출"]}]
    )
    actual = gold_item(checklistItems=[{"content": "동의서를 담임선생님께 제출하기"}])
    assert evaluate_sample(parse_sample(record(expected)), response(actual))["checklist_f1"] == 1


def test_local_source_hash_size_and_order_are_checked(tmp_path):
    first = tmp_path / "a.pdf"
    second = tmp_path / "b.png"
    first.write_bytes(b"%PDF-1.4")
    second.write_bytes(b"png")
    raw = record(
        sourceFiles=[
            {"path": "a.pdf", "sha256": sha256(first.read_bytes())},
            {"path": "b.png", "sha256": sha256(second.read_bytes())},
        ],
        _baseDir=tmp_path,
    )
    sample = parse_sample(raw)
    assert [doc.mime_type for doc in load_local_documents(sample, max_bytes=100)] == [
        "application/pdf",
        "image/png",
    ]
    with pytest.raises(ValueError, match="DOCUMENT_SIZE_LIMIT"):
        load_local_documents(sample, max_bytes=2)
    first.write_bytes(b"changed")
    with pytest.raises(ValueError, match="SOURCE_FILE_CHANGED"):
        load_local_documents(sample, max_bytes=100)


def test_attachment_fallback_is_counted_as_failure_not_scored(tmp_path, monkeypatch):
    source = tmp_path / "one.pdf"
    source.write_bytes(b"%PDF-1.4")
    sample = parse_sample(record(sourceFiles=[{"path": str(source)}]))
    monkeypatch.setattr(evaluator, "analyze_newsletter", lambda *_args, **_kwargs: response())
    report = evaluator.evaluate_samples([sample], mode="openai", with_documents=True)
    assert report["failed_sample_count"] == 1
    assert report["item_f1"] == 0
    assert report["samples"][0]["error"] == "DOCUMENT_ATTACHMENT_FAILED"


def test_failure_counts_and_environment_restored_without_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_ENABLED", "true")

    def fail(*args, **kwargs):
        raise RuntimeError("secret_signed_url")

    monkeypatch.setattr(evaluator, "analyze_newsletter", fail)
    report = evaluator.evaluate_samples([parse_sample(record())], mode="baseline")
    assert report["sample_count"] == 1
    assert report["item_f1"] == 0
    assert "secret_signed_url" not in json.dumps(report)
    import os

    assert os.environ["OPENAI_ENABLED"] == "true"


def test_document_preflight_happens_before_any_model_call(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("model must not be called")

    monkeypatch.setattr(evaluator, "analyze_newsletter", fail)
    with pytest.raises(ValueError, match="MISSING_SOURCE_FILES"):
        evaluator.evaluate_samples([parse_sample(record())], mode="openai", with_documents=True)


def test_validate_only_makes_no_calls_and_duplicate_ids_rejected(tmp_path, monkeypatch):
    path = tmp_path / "sample.json"
    path.write_text(json.dumps(record()), encoding="utf-8")
    monkeypatch.setattr(evaluator, "analyze_newsletter", lambda *_a, **_kw: pytest.fail("no calls"))
    assert evaluator.main([str(path), "--validate-only"]) == 0
    path.write_text(json.dumps([record(), record()]), encoding="utf-8")
    with pytest.raises(ValueError, match="DUPLICATE_SAMPLE_ID"):
        load_samples(path)


def test_real_baseline_cli_writes_json_including_candidate_dates(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_ENABLED", "true")
    dataset = tmp_path / "sample.json"
    dataset.write_text(json.dumps(record()), encoding="utf-8")
    output = tmp_path / "report.json"
    assert evaluator.main([str(dataset), "--report-output", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["failed_sample_count"] == 0
    assert report["samples"][0]["prediction"]["items"]
    assert report["reproducibility"]["model"] is None


def test_migration_keeps_no_ocr_as_pending_and_removes_invented_time():
    raw = {
        "documentId": "pilot_001",
        "originalText": None,
        "dateCandidates": [],
        "expected": {"items": [gold_item(datetime="2026-09-28T23:59:59+09:00")]},
    }
    migrated = migrate_sample(raw)
    assert migrated["input"] is None
    assert migrated["metadata"]["inputStatus"] == "pending_actual_ocr"
    assert migrated["expected"]["items"][0]["datetime"] == "2026-09-28"
    assert "confidence" not in migrated["expected"]["items"][0]


def test_migration_does_not_invent_empty_gold_for_raw_ocr_results():
    with pytest.raises(ValueError, match="MISSING_EXPECTED_ITEMS"):
        migrate_sample(be_result())


def test_prepare_joins_by_id_and_never_overwrites_gold(tmp_path):
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps(record()), encoding="utf-8")
    ocr = tmp_path / "ocr"
    ocr.mkdir()
    (ocr / "pilot_001.json").write_text(json.dumps(be_result()), encoding="utf-8")
    output = tmp_path / "ready.json"
    prepared = prepare(labels, output, ocr)
    assert prepared[0]["input"]["originalText"] == record()["input"]["originalText"]
    assert json.loads(labels.read_text(encoding="utf-8")) == record()
    with pytest.raises(FileExistsError):
        prepare(labels, output, ocr)


def test_prepare_keeps_relative_source_paths_valid_when_output_moves(tmp_path):
    labels = tmp_path / "labels.json"
    raw = record(sourceFiles=[{"path": "original.pdf"}])
    labels.write_text(json.dumps(raw), encoding="utf-8")
    prepared = prepare(labels, tmp_path / "other" / "labels.json")
    assert Path(prepared[0]["sourceFiles"][0]["path"]) == tmp_path / "original.pdf"


def test_document_success_records_real_attachment_count_and_hash(tmp_path, monkeypatch):
    source = tmp_path / "one.pdf"
    source.write_bytes(b"%PDF-1.4")
    sample = parse_sample(record(sourceFiles=[{"path": str(source)}]))

    def analyze(request, documents):
        assert len(documents) == 1
        assert documents[0].content == b"%PDF-1.4"
        return response(meta={"attachedDocumentCount": 1})

    monkeypatch.setattr(evaluator, "analyze_newsletter", analyze)
    report = evaluator.evaluate_samples([sample], mode="openai", with_documents=True)
    assert report["failed_sample_count"] == 0
    assert report["samples"][0]["attached_document_count"] == 1
    assert report["samples"][0]["document_sha256"] == [sha256(b"%PDF-1.4")]


def test_validation_reports_safe_sample_id_and_code(tmp_path, capsys):
    raw = record()
    raw["input"]["dateCandidates"][0]["endOffset"] = 1000
    labels = tmp_path / "bad.json"
    labels.write_text(json.dumps(raw), encoding="utf-8")
    assert evaluator.main([str(labels), "--validate-only"]) == 2
    assert "pilot_001: CANDIDATE_TEXT_MISMATCH" in capsys.readouterr().err


@pytest.mark.parametrize(
    "changes",
    [
        {"type": "checklist"},
        {"type": "reminder"},
        {"dateStatus": "missing"},
        {"endDatetime": "2026-09-28"},
        {"needsUserConfirmation": True},
    ],
)
def test_invalid_expected_contract_rejected(changes):
    with pytest.raises(ValueError):
        parse_sample(record(gold_item(**changes)))


def test_model_delay_only_between_samples_and_never_for_baseline(monkeypatch):
    calls = []
    monkeypatch.setattr(evaluator.time, "sleep", calls.append)
    monkeypatch.setattr(evaluator, "analyze_newsletter", lambda *_a, **_kw: response())
    samples = [parse_sample(record()), parse_sample(record(sampleId="pilot_002"))]
    report = evaluator.evaluate_samples(samples, mode="openai", delay_seconds=40)
    assert calls == [40]
    assert report["delay_seconds"] == 40
    calls.clear()
    evaluator.evaluate_samples(samples, mode="baseline", delay_seconds=40)
    assert calls == []


@pytest.mark.parametrize("delay", [-1, float("nan"), float("inf")])
def test_invalid_delay_rejected_before_model_call(delay, monkeypatch):
    monkeypatch.setattr(evaluator, "analyze_newsletter", lambda *_a, **_kw: pytest.fail("no calls"))
    with pytest.raises(ValueError, match="INVALID_DELAY_SECONDS"):
        evaluator.evaluate_samples([parse_sample(record())], mode="openai", delay_seconds=delay)


def test_pilot_source_review_has_no_synthesized_input_and_no_invented_tasks():
    from scripts.newsletter_eval_data import parse_label_item

    path = Path(__file__).resolve().parents[1] / "data/newsletter-pilot/pilot-labels-v3.json"
    samples = json.loads(path.read_text(encoding="utf-8"))["samples"]
    assert len(samples) == 10
    by_id = {sample["sampleId"]: sample for sample in samples}
    for sample in samples:
        assert sample["input"] is None
        assert sample["metadata"]["annotationStatus"] == "reviewed"
        assert sample["metadata"]["reviewMethod"] == "assistant_visual_source_review"
        assert sample["metadata"]["reviewNotes"]
        for item in sample["expected"]["items"]:
            parse_label_item(item)
    assert by_id["pilot_005"]["expected"]["items"] == []
    assert by_id["pilot_009"]["expected"]["items"] == []
    assert len(by_id["pilot_004"]["expected"]["items"]) == 1
    fire = by_id["pilot_008"]["expected"]["items"][0]
    assert fire["type"] == "reminder" and fire["datetime"] is None
    assert len(fire["checklistItems"]) == 1
