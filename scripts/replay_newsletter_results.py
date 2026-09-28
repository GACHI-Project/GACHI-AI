"""Recheck saved suite responses offline. This does NOT evaluate the new prompt."""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import NewsletterAnalysisRequest, NewsletterAnalysisResponse  # noqa: E402
from app.services.newsletter_validation import normalize_analysis_dates  # noqa: E402


def evaluate(response: NewsletterAnalysisResponse, expected: dict) -> dict[str, bool]:
    items = response.items
    confirmed = [i for i in items if i.date_status == "confirmed" and i.datetime]
    dates = {i.datetime[:10] for i in confirmed}
    checks = {"summaryPresent": bool(response.summary.strip())}
    if expected.get("emptyItems"):
        checks["emptyItems"] = not items
    if expected.get("undatedOnly"):
        checks["undatedOnly"] = bool(items) and all(
            i.type == "reminder"
            and i.date_status == "missing"
            and i.datetime is None
            and i.selected_date_candidate is None
            and not i.needs_user_confirmation
            for i in items
        )
    if expected.get("ambiguousOnly"):
        checks["ambiguousOnly"] = bool(items) and all(
            i.date_status == "ambiguous"
            and i.datetime is None
            and i.selected_date_candidate is None
            and i.needs_user_confirmation
            for i in items
        )
    if expected.get("needsAmbiguous"):
        checks["ambiguousDeadline"] = any(
            i.type == "deadline" and i.date_status == "ambiguous" and i.checklist_items
            for i in items
        )
    for day in expected.get("requiredDates", []):
        checks[f"date:{day}"] = day in dates
    for day in expected.get("forbiddenDates", []):
        checks[f"exclude:{day}"] = day not in dates
    if "exactItemCount" in expected:
        checks["itemCount"] = len(items) == expected["exactItemCount"]
    for kind, day in expected.get("typedDates", []):
        checks[f"type:{kind}:{day}"] = any(
            i.type == kind and i.datetime[:10] == day for i in confirmed
        )
    for day, time in expected.get("requiredTimes", []):
        checks[f"time:{day}:{time}"] = any(i.datetime[:16] == f"{day}T{time}" for i in confirmed)
    contents = "\n".join(c.content for i in items for c in i.checklist_items)
    details = "\n".join(c.detail or "" for i in items for c in i.checklist_items)
    for pattern in expected.get("requiredActionPatterns", []):
        checks[f"action:{pattern}"] = bool(re.search(pattern, contents + "\n" + details))
    for pattern in expected.get("requiredDetailPatterns", []):
        checks[f"detail:{pattern}"] = bool(re.search(pattern, details))
    for pattern in expected.get("forbiddenActionPatterns", []):
        checks[f"noAction:{pattern}"] = not bool(re.search(pattern, contents))
    if expected.get("noActionsOnSchedule"):
        checks["noActionsOnSchedule"] = all(
            not i.checklist_items for i in items if i.type == "schedule"
        )
    return checks


def replay(directory: Path, phase: str, *, documents_attached: bool = False) -> list[dict]:
    rows = []
    for source in sorted(directory.glob("*-input.json")):
        case = json.loads(source.read_text(encoding="utf-8-sig"))
        case_id = source.name.removesuffix("-input.json")
        request = NewsletterAnalysisRequest.model_validate(case["request"])
        suffix = "final" if phase == "final" else f"{phase}-raw"
        outputs = sorted(directory.glob(f"{case_id}-run-*-{suffix}.json"))
        # A missing response is a failure, never silently excluded from the denominator.
        if not outputs:
            rows.append({"case": case_id, "error": "MISSING_RESPONSE", "passed": False})
        for output in outputs:
            try:
                raw = NewsletterAnalysisResponse.model_validate_json(
                    output.read_text(encoding="utf-8-sig")
                )
                result = normalize_analysis_dates(
                    request, raw, documents_attached=documents_attached
                )
                before = evaluate(raw, case["expected"])
                after = evaluate(result, case["expected"])
                rows.append(
                    {
                        "case": output.stem,
                        "passed": all(after.values()),
                        "beforeChecks": before,
                        "afterChecks": after,
                        "warnings": result.meta.get("dateValidationWarnings", []),
                        "manualReview": case["expected"].get("review", ""),
                    }
                )
            except ValueError:
                rows.append({"case": output.stem, "error": "INVALID_RESPONSE", "passed": False})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--phase", choices=["draft", "review", "final"], default="draft")
    parser.add_argument("--documents-attached", action="store_true")
    args = parser.parse_args()
    rows = replay(args.directory, args.phase, documents_attached=args.documents_attached)
    print(
        json.dumps(
            {
                "mode": "offline-replay-not-new-prompt-evaluation",
                "passed": sum(row["passed"] for row in rows),
                "total": len(rows),
                "results": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if rows and all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
