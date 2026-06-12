import json

import pandas as pd

from hft_cli import main
from reports.quote_lifecycle import QuoteLifecycleThresholds, evaluate_quote_lifecycle, write_quote_lifecycle_plan


def two_snapshot_quotes():
    return pd.DataFrame(
        [
            {"ts": 1_000, "instrument_id": "CALL_1000", "side": 1, "price": 10.00, "qty": 75},
            {"ts": 1_000, "instrument_id": "CALL_1000", "side": -1, "price": 10.50, "qty": 75},
            {"ts": 1_000, "instrument_id": "PUT_1000", "side": 1, "price": 9.00, "qty": 75},
            {"ts": 1_000, "instrument_id": "PUT_1000", "side": -1, "price": 9.50, "qty": 75},
            {"ts": 2_000, "instrument_id": "CALL_1000", "side": 1, "price": 10.05, "qty": 75},
            {"ts": 2_000, "instrument_id": "CALL_1000", "side": -1, "price": 10.50, "qty": 75},
        ]
    )


def write_quote_risk(path, *, passed=True):
    path.mkdir()
    pd.DataFrame(
        [
            {
                "all_passed": passed,
                "quotes": 6,
                "marketable_quotes": 0,
                "min_quote_edge": 0.15,
            }
        ]
    ).to_csv(path / "quote_risk_summary.csv", index=False)


def test_quote_lifecycle_plans_submits_replaces_and_cancels():
    report = evaluate_quote_lifecycle(
        two_snapshot_quotes(),
        thresholds=QuoteLifecycleThresholds(
            max_order_messages=10,
            max_active_quotes=4,
            max_messages_per_snapshot=4,
            max_replaces=1,
            max_cancels=4,
        ),
    )

    summary = report.summary.iloc[0]
    assert report.ready
    assert int(summary["submits"]) == 4
    assert int(summary["replaces"]) == 1
    assert int(summary["cancels"]) == 4
    assert int(summary["order_messages"]) == 10
    assert report.actions["action"].tolist() == [
        "submit",
        "submit",
        "submit",
        "submit",
        "replace",
        "cancel",
        "cancel",
        "cancel",
        "cancel",
    ]
    assert report.summary.iloc[0]["recommendation"] == "route_with_lifecycle_controls"


def test_quote_lifecycle_cancels_and_resubmits_on_ttl_expiry():
    quotes = pd.DataFrame(
        [
            {"ts": 1_000, "instrument_id": "CALL_1000", "side": 1, "price": 10.00, "qty": 75},
            {"ts": 3_000, "instrument_id": "CALL_1000", "side": 1, "price": 10.00, "qty": 75},
        ]
    )

    report = evaluate_quote_lifecycle(
        quotes,
        thresholds=QuoteLifecycleThresholds(quote_ttl_ns=1_000),
    )

    assert report.actions["action"].tolist() == ["submit", "cancel", "submit", "cancel"]
    assert report.actions["reason"].tolist() == ["new_quote", "quote_ttl_expired", "new_quote", "end_of_plan"]
    assert int(report.summary.loc[0, "order_messages"]) == 4


def test_write_quote_lifecycle_outputs_artifacts_and_manifest(tmp_path):
    quotes_path = tmp_path / "surface_quotes.csv"
    review_dir = tmp_path / "quote_review"
    out_dir = tmp_path / "quote_lifecycle"
    two_snapshot_quotes().to_csv(quotes_path, index=False)
    write_quote_risk(review_dir, passed=True)

    report = write_quote_lifecycle_plan(
        quotes_path,
        output_dir=out_dir,
        thresholds=QuoteLifecycleThresholds(max_order_messages=10),
        quote_risk_review_dir=review_dir,
        require_quote_risk_review=True,
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.output_dir == out_dir
    assert (out_dir / "quote_lifecycle_actions.csv").exists()
    assert (out_dir / "quote_lifecycle_snapshots.csv").exists()
    assert (out_dir / "quote_lifecycle_checks.csv").exists()
    assert (out_dir / "quote_lifecycle_summary.csv").exists()
    assert report.ready
    assert manifest["parameters"]["require_quote_risk_review"]
    assert "quote_risk_review" in manifest["inputs"]


def test_cli_quote_lifecycle_fails_when_required_quote_review_is_missing(tmp_path):
    quotes_path = tmp_path / "surface_quotes.csv"
    out_dir = tmp_path / "cli_quote_lifecycle"
    two_snapshot_quotes().to_csv(quotes_path, index=False)

    code = main(
        [
            "plan-quote-lifecycle",
            "--quotes",
            str(quotes_path),
            "--out",
            str(out_dir),
            "--require-quote-risk-review",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "quote_lifecycle_summary.csv")
    checks = pd.read_csv(out_dir / "quote_lifecycle_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert checks.loc[0, "check"] == "quote_risk_review"
    assert checks.loc[0, "reason"] == "quote_risk_review_missing"
