import json
from pathlib import Path

import pandas as pd
import pytest

from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.manifest import (
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.research_family import ResearchFamilyConfig, write_research_family_audit
from reports.research_family_launch import (
    load_research_family_launch_attempt_ledger,
    load_research_family_launch_contract,
    load_research_family_launch_execution_receipt,
    load_research_family_launch_matrix,
    load_research_family_launch_outcome_ledger,
    write_research_family_launch_attempt_outcome,
    write_research_family_launch_execution_receipt,
    write_research_family_launch_matrix,
)
from reports.research_family_registration import write_research_family_registration


def test_research_family_launch_builds_deterministic_pending_contracts(tmp_path):
    registration, registration_dir = _write_registration(tmp_path)

    first = write_research_family_launch_matrix(
        registration_dir,
        output_dir=tmp_path / "launches",
    )
    second = write_research_family_launch_matrix(
        registration_dir,
        output_dir=tmp_path / "launches_copy",
    )

    summary = first.summary.iloc[0]
    assert registration.passed
    assert not first.passed
    assert int(summary["valid_contract_count"]) == 2
    assert int(summary["contract_ready_count"]) == 2
    assert int(summary["never_launched_count"]) == 2
    assert int(summary["closure_covered_count"]) == 0
    assert summary["next_gate"] == "run-research-family-study"
    assert first.launches["contract_valid"].astype(bool).all()
    assert first.launches["sweep_inputs_current"].astype(bool).all()
    assert first.launches["contract_id"].tolist() == second.launches[
        "contract_id"
    ].tolist()
    for row in first.launches.itertuples(index=False):
        argv = json.loads(row.launch_argv_json)
        assert "--require-research-registration" in argv
        assert "--registered-study-label" in argv
        assert "--research-launch-matrix" in argv
        assert "--research-launch-contract-id" in argv
        assert "--require-research-launch-contract" in argv
        assert "--require-research-launch-execution-receipt" in argv
        assert "--fail-on-breach" in argv
        assert not bool(row.authorizes_submission)
        contract = json.loads(
            Path(row.contract_path).read_text(encoding="utf-8")
        )
        assert contract["contract_id"] == row.contract_id
        assert not contract["authorizes_submission"]


def test_research_family_launch_executes_and_binds_exact_contract(tmp_path):
    _, registration_dir = _write_registration(tmp_path)
    launch_dir = tmp_path / "launches"
    pending = write_research_family_launch_matrix(
        registration_dir,
        output_dir=launch_dir,
    )
    contract = pending.launches.set_index("study_label").loc["leadlag"]

    status = main(
        [
            "run-research-family-study",
            "--launch-matrix",
            str(launch_dir),
            "--contract-id",
            str(contract["contract_id"]),
        ]
    )

    result_root = tmp_path / "results" / "leadlag"
    summary = pd.read_csv(
        result_root / "robust_selection_pipeline_summary.csv"
    ).iloc[0]
    binding = pd.read_csv(
        result_root / "robust_selection_pipeline_research_launch_contract.csv"
    ).iloc[0]
    receipt_binding = pd.read_csv(
        result_root
        / "robust_selection_pipeline_research_launch_execution_receipt.csv"
    ).iloc[0]
    manifest = json.loads((result_root / "manifest.json").read_text(encoding="utf-8"))
    assert status == 0
    assert bool(summary["ready"])
    assert bool(summary["research_launch_contract_passed"])
    assert bool(summary["research_launch_execution_receipt_passed"])
    assert summary["research_launch_execution_receipt_id"]
    assert summary["research_launch_dispatch_id"]
    assert summary["research_launch_attempt_id"]
    assert int(summary["research_launch_attempt_number"]) == 1
    assert summary["research_launch_attempt_record_sha256"]
    assert summary["research_launch_semantic_sha256"]
    assert summary["research_launch_contract_id"] == contract["contract_id"]
    assert bool(binding["passed"])
    assert bool(binding["sweep_paths_match"])
    assert bool(binding["group_columns_match"])
    assert bool(receipt_binding["passed"])
    assert bool(receipt_binding["attempt_ledger_matches"])
    assert bool(receipt_binding["argv_matches"])
    assert bool(receipt_binding["semantic_matches"])
    assert manifest["inputs"]["research_family_launch_contract"]["sha256"] == (
        file_sha256(Path(str(contract["contract_path"])))
    )
    assert manifest["inputs"]["research_family_launch_execution_receipt"][
        "kind"
    ] == "file"
    assert manifest["inputs"]["research_family_launch_attempt_record"][
        "kind"
    ] == "file"
    ledger = load_research_family_launch_attempt_ledger(launch_dir)
    outcome_ledger = load_research_family_launch_outcome_ledger(launch_dir)
    assert ledger.attempt_count == 1
    assert outcome_ledger.outcome_count == 1
    assert outcome_ledger.records[0]["outcome_status"] == "completed_ready"
    assert int(outcome_ledger.records[0]["exit_status"]) == 0
    assert ledger.records[0]["attempt_id"] == summary["research_launch_attempt_id"]
    duplicate_status = main(
        [
            "run-research-family-study",
            "--launch-matrix",
            str(launch_dir),
            "--contract-id",
            str(contract["contract_id"]),
        ]
    )
    completed_retry_status = main(
        [
            "run-research-family-study",
            "--launch-matrix",
            str(launch_dir),
            "--contract-id",
            str(contract["contract_id"]),
            "--retry-of-attempt-id",
            str(ledger.records[0]["attempt_id"]),
            "--retry-reason",
            "repeat completed result",
            "--attest-retry",
        ]
    )
    assert duplicate_status == 2
    assert completed_retry_status == 2
    assert load_research_family_launch_attempt_ledger(launch_dir).attempt_count == 1
    refreshed = write_research_family_launch_matrix(
        registration_dir,
        output_dir=launch_dir,
    )
    refreshed_leadlag = refreshed.launches.set_index("study_label").loc[
        "leadlag"
    ]
    root_integrity = verify_experiment_manifest(
        result_root / "manifest.json",
        expected_run_type="robust_selection_pipeline",
        require_input_fingerprints=True,
    )
    assert refreshed_leadlag["study_status"] == "completed_ready"
    assert bool(refreshed_leadlag["result_launch_contract_bound"])
    assert bool(refreshed_leadlag["result_launch_execution_receipt_bound"])
    assert bool(refreshed_leadlag["result_launch_attempt_bound"])
    assert bool(refreshed_leadlag["result_launch_outcome_bound"])
    assert refreshed_leadlag["latest_outcome_status"] == "completed_ready"
    assert root_integrity.passed
    result_summary_path = result_root / "robust_selection_pipeline_summary.csv"
    result_summary_path.write_text(
        result_summary_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    drifted_matrix = load_research_family_launch_matrix(launch_dir)
    assert not drifted_matrix.manifest_current
    assert drifted_matrix.manifest_error == "input_drift"
    with pytest.raises(ValueError, match="result summary drifted"):
        load_research_family_launch_outcome_ledger(launch_dir)


def test_research_family_launch_recovers_unfinalized_completed_result(tmp_path):
    _, registration_dir = _write_registration(tmp_path)
    launch_dir = tmp_path / "launches"
    pending = write_research_family_launch_matrix(
        registration_dir,
        output_dir=launch_dir,
    )
    row = pending.launches.set_index("study_label").loc["leadlag"]
    contract = load_research_family_launch_contract(
        launch_dir,
        str(row["contract_id"]),
    )
    receipt = write_research_family_launch_execution_receipt(contract)
    direct_status = main(
        [
            *contract.argv,
            "--research-launch-execution-receipt",
            str(receipt.path),
        ][3:]
    )
    unfinalized = write_research_family_launch_matrix(
        registration_dir,
        output_dir=launch_dir,
    )
    unfinalized_row = unfinalized.launches.set_index("study_label").loc[
        "leadlag"
    ]
    assert direct_status == 0
    assert unfinalized_row["study_status"] == "completed_unfinalized"
    assert not bool(unfinalized_row["result_launch_outcome_bound"])

    missing_attestation = main(
        [
            "recover-research-family-study-outcome",
            "--launch-matrix",
            str(launch_dir),
            "--attempt-id",
            receipt.attempt_id,
            "--exit-status",
            "0",
            "--recovery-reason",
            "executor stopped after writing the result manifest",
        ]
    )
    inconsistent_status = main(
        [
            "recover-research-family-study-outcome",
            "--launch-matrix",
            str(launch_dir),
            "--attempt-id",
            receipt.attempt_id,
            "--exit-status",
            "2",
            "--recovery-reason",
            "executor stopped after writing the result manifest",
            "--attest-recovery",
        ]
    )
    assert missing_attestation == 2
    assert inconsistent_status == 2
    assert load_research_family_launch_outcome_ledger(launch_dir).outcome_count == 0

    recovered_status = main(
        [
            "recover-research-family-study-outcome",
            "--launch-matrix",
            str(launch_dir),
            "--attempt-id",
            receipt.attempt_id,
            "--exit-status",
            "0",
            "--recovery-reason",
            "executor stopped after writing the result manifest",
            "--attest-recovery",
        ]
    )
    outcomes = load_research_family_launch_outcome_ledger(launch_dir)
    assert recovered_status == 0
    assert outcomes.outcome_count == 1
    assert bool(outcomes.records[0]["recovered"])
    assert outcomes.records[0]["outcome_status"] == "completed_ready"
    assert outcomes.records[0]["recovery_reason"]

    completed = write_research_family_launch_matrix(
        registration_dir,
        output_dir=launch_dir,
    )
    completed_row = completed.launches.set_index("study_label").loc["leadlag"]
    assert completed_row["study_status"] == "completed_ready"
    assert bool(completed_row["result_launch_outcome_bound"])
    assert bool(completed_row["latest_outcome_recovered"])
    duplicate_recovery = main(
        [
            "recover-research-family-study-outcome",
            "--launch-matrix",
            str(launch_dir),
            "--attempt-id",
            receipt.attempt_id,
            "--exit-status",
            "0",
            "--recovery-reason",
            "duplicate recovery",
            "--attest-recovery",
        ]
    )
    assert duplicate_recovery == 2
    assert load_research_family_launch_outcome_ledger(launch_dir).outcome_count == 1


def test_research_family_launch_blocks_contract_argument_drift(tmp_path):
    _, registration_dir = _write_registration(tmp_path)
    launch_dir = tmp_path / "launches"
    pending = write_research_family_launch_matrix(
        registration_dir,
        output_dir=launch_dir,
    )
    contract = pending.launches.set_index("study_label").loc["leadlag"]
    argv = json.loads(contract["launch_argv_json"])
    first_sweep = argv.index("--sweeps") + 1
    argv[first_sweep], argv[first_sweep + 1] = (
        argv[first_sweep + 1],
        argv[first_sweep],
    )

    status = main(argv[3:])

    result_root = tmp_path / "results" / "leadlag"
    summary = pd.read_csv(
        result_root / "robust_selection_pipeline_summary.csv"
    ).iloc[0]
    binding = pd.read_csv(
        result_root / "robust_selection_pipeline_research_launch_contract.csv"
    ).iloc[0]
    assert status == 2
    assert not bool(summary["ready"])
    assert summary["next_gate"] == "run-research-family-study"
    assert not bool(binding["passed"])
    assert not bool(binding["sweep_paths_match"])
    assert "sweep_paths_match" in binding["failed_check_names"]


def test_research_family_launch_receipt_blocks_semantic_parameter_drift(tmp_path):
    _, registration_dir = _write_registration(tmp_path)
    launch_dir = tmp_path / "launches"
    pending = write_research_family_launch_matrix(
        registration_dir,
        output_dir=launch_dir,
    )
    row = pending.launches.set_index("study_label").loc["leadlag"]
    contract = load_research_family_launch_contract(
        launch_dir,
        str(row["contract_id"]),
    )
    receipt = write_research_family_launch_execution_receipt(contract)
    drifted_argv = [
        *contract.argv,
        "--research-launch-execution-receipt",
        str(receipt.path),
        "--max-probability-overfit",
        "0.20",
    ]

    status = main(drifted_argv[3:])

    result_root = tmp_path / "results" / "leadlag"
    summary = pd.read_csv(
        result_root / "robust_selection_pipeline_summary.csv"
    ).iloc[0]
    receipt_binding = pd.read_csv(
        result_root
        / "robust_selection_pipeline_research_launch_execution_receipt.csv"
    ).iloc[0]
    assert status == 2
    assert not bool(summary["ready"])
    assert summary["next_gate"] == "run-research-family-study"
    assert bool(receipt_binding["argv_matches"])
    assert not bool(receipt_binding["semantic_matches"])
    assert "semantic_matches" in receipt_binding["failed_check_names"]


def test_research_family_launch_requires_attested_latest_incomplete_retry(tmp_path):
    _, registration_dir = _write_registration(tmp_path)
    launch_dir = tmp_path / "launches"
    pending = write_research_family_launch_matrix(
        registration_dir,
        output_dir=launch_dir,
    )
    row = pending.launches.set_index("study_label").loc["leadlag"]
    contract_id = str(row["contract_id"])
    first_receipt = write_research_family_launch_execution_receipt(
        load_research_family_launch_contract(launch_dir, contract_id)
    )
    interrupted = write_research_family_launch_attempt_outcome(
        first_receipt,
        exit_status=1,
        execution_completed=False,
        exception_type="RuntimeError",
    )

    refreshed = write_research_family_launch_matrix(
        registration_dir,
        output_dir=launch_dir,
    )
    refreshed_row = refreshed.launches.set_index("study_label").loc["leadlag"]
    assert interrupted.outcome_status == "interrupted"
    assert refreshed_row["study_status"] == "attempt_interrupted"
    assert bool(refreshed_row["retry_ready"])
    assert int(refreshed_row["attempt_count"]) == 1
    assert int(refreshed_row["outcome_count"]) == 1
    assert refreshed_row["latest_outcome_status"] == "interrupted"
    assert refreshed_row["latest_attempt_id"] == first_receipt.attempt_id

    wrong_retry = main(
        [
            "run-research-family-study",
            "--launch-matrix",
            str(launch_dir),
            "--contract-id",
            contract_id,
            "--retry-of-attempt-id",
            "not-the-latest-attempt",
            "--retry-reason",
            "worker interrupted",
            "--attest-retry",
        ]
    )
    unattested_retry = main(
        [
            "run-research-family-study",
            "--launch-matrix",
            str(launch_dir),
            "--contract-id",
            contract_id,
            "--retry-of-attempt-id",
            first_receipt.attempt_id,
            "--retry-reason",
            "worker interrupted",
        ]
    )
    assert wrong_retry == 2
    assert unattested_retry == 2
    assert load_research_family_launch_attempt_ledger(launch_dir).attempt_count == 1

    retry_status = main(
        [
            "run-research-family-study",
            "--launch-matrix",
            str(launch_dir),
            "--contract-id",
            contract_id,
            "--retry-of-attempt-id",
            first_receipt.attempt_id,
            "--retry-reason",
            "worker interrupted before the pipeline started",
            "--attest-retry",
        ]
    )

    ledger = load_research_family_launch_attempt_ledger(launch_dir)
    outcomes = load_research_family_launch_outcome_ledger(launch_dir)
    result_summary = pd.read_csv(
        tmp_path / "results" / "leadlag" / "robust_selection_pipeline_summary.csv"
    ).iloc[0]
    assert retry_status == 0
    assert ledger.attempt_count == 2
    assert outcomes.outcome_count == 2
    assert outcomes.records[1]["outcome_status"] == "completed_ready"
    assert ledger.records[1]["retry_of_attempt_id"] == first_receipt.attempt_id
    assert bool(ledger.records[1]["retry_attested"])
    assert int(result_summary["research_launch_attempt_number"]) == 2
    assert (
        result_summary["research_launch_retry_of_attempt_id"]
        == first_receipt.attempt_id
    )
    assert bool(result_summary["research_launch_retry_attested"])
    assert load_research_family_launch_matrix(launch_dir).manifest_current
    completed = write_research_family_launch_matrix(
        registration_dir,
        output_dir=launch_dir,
    )
    completed_row = completed.launches.set_index("study_label").loc["leadlag"]
    assert completed_row["study_status"] == "completed_ready"
    assert int(completed_row["attempt_count"]) == 2
    assert bool(completed_row["result_launch_attempt_bound"])

    abandonments = tmp_path / "abandonments.csv"
    pd.DataFrame(
        [{"study_label": "imbalance", "reason": "feed history was unavailable"}]
    ).to_csv(abandonments, index=False)
    closed = write_research_family_launch_matrix(
        registration_dir,
        output_dir=launch_dir,
        abandonment_path=abandonments,
        attest_abandonments=True,
    )
    family = write_research_family_audit(
        [tmp_path / "results" / "leadlag"],
        labels=["leadlag"],
        output_dir=tmp_path / "family",
        registration_path=registration_dir,
        launch_matrix_path=launch_dir,
        config=ResearchFamilyConfig(
            family_id="launch_matrix_family",
            declaration_complete_attested=True,
            require_prospective_registration=True,
            require_launch_coverage=True,
        ),
    )
    census = pd.read_csv(
        tmp_path / "family" / "research_family_launch_attempt_census.csv"
    ).sort_values("attempt_number")
    family_summary = family.summary.iloc[0]
    family_row = family.studies.set_index("study_label").loc["leadlag"]
    assert closed.passed
    assert family.passed
    assert census["attempt_number"].astype(int).tolist() == [1, 2]
    assert census["outcome_status"].tolist() == [
        "interrupted",
        "completed_ready",
    ]
    assert census["is_operational_retry"].astype(bool).tolist() == [False, True]
    assert not census["counts_as_additional_hypothesis"].astype(bool).any()
    assert not census["authorizes_submission"].astype(bool).any()
    assert int(family_summary["study_count"]) == 2
    assert int(family_summary["launch_attempt_count"]) == 2
    assert int(family_summary["launch_outcome_count"]) == 2
    assert int(family_summary["launch_operational_retry_count"]) == 1
    assert int(family_summary["launch_interrupted_attempt_count"]) == 1
    assert int(family_summary["launch_additional_retry_hypothesis_count"]) == 0
    assert not bool(
        family_summary[
            "operational_retries_count_as_additional_hypotheses"
        ]
    )
    assert int(family_row["launch_attempt_count"]) == 2
    assert int(family_row["launch_retry_count"]) == 1
    assert int(family_row["launch_outcome_count"]) == 2
    assert int(family_row["launch_interrupted_count"]) == 1
    assert family_row["launch_latest_attempt_id"] == ledger.records[1][
        "attempt_id"
    ]
    assert family_row["launch_latest_outcome_status"] == "completed_ready"


def test_research_family_launch_rejects_tampered_attempt_chain(tmp_path):
    _, registration_dir = _write_registration(tmp_path)
    launch_dir = tmp_path / "launches"
    pending = write_research_family_launch_matrix(
        registration_dir,
        output_dir=launch_dir,
    )
    row = pending.launches.set_index("study_label").loc["leadlag"]
    contract_id = str(row["contract_id"])
    receipt = write_research_family_launch_execution_receipt(
        load_research_family_launch_contract(launch_dir, contract_id)
    )
    ledger_path = launch_dir / "executions" / "attempts.jsonl"
    record = json.loads(ledger_path.read_text(encoding="utf-8").strip())
    record["retry_reason"] = "tampered after append"
    ledger_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="digest is invalid"):
        load_research_family_launch_attempt_ledger(launch_dir)
    blocked_matrix = write_research_family_launch_matrix(
        registration_dir,
        output_dir=launch_dir,
    )
    ledger_check = blocked_matrix.checks.set_index("check").loc[
        "attempt_ledger_integrity"
    ]
    assert not blocked_matrix.passed
    assert not bool(ledger_check["passed"])
    assert blocked_matrix.summary.iloc[0]["next_gate"] == (
        "plan-research-family-launches"
    )
    status = main(
        [
            "run-research-family-study",
            "--launch-matrix",
            str(launch_dir),
            "--contract-id",
            contract_id,
            "--retry-of-attempt-id",
            receipt.attempt_id,
            "--retry-reason",
            "recover interrupted worker",
            "--attest-retry",
        ]
    )
    assert status == 2
    assert len(ledger_path.read_text(encoding="utf-8").splitlines()) == 1


def test_research_family_launch_rejects_tampered_outcome_chain(tmp_path):
    _, registration_dir = _write_registration(tmp_path)
    launch_dir = tmp_path / "launches"
    pending = write_research_family_launch_matrix(
        registration_dir,
        output_dir=launch_dir,
    )
    row = pending.launches.set_index("study_label").loc["leadlag"]
    receipt = write_research_family_launch_execution_receipt(
        load_research_family_launch_contract(
            launch_dir,
            str(row["contract_id"]),
        )
    )
    write_research_family_launch_attempt_outcome(
        receipt,
        exit_status=1,
        execution_completed=False,
        exception_type="RuntimeError",
    )
    ledger_path = launch_dir / "executions" / "outcomes.jsonl"
    outcome = json.loads(ledger_path.read_text(encoding="utf-8").strip())
    outcome["exception_type"] = "TamperedError"
    ledger_path.write_text(json.dumps(outcome) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="digest is invalid"):
        load_research_family_launch_outcome_ledger(launch_dir)
    blocked = write_research_family_launch_matrix(
        registration_dir,
        output_dir=launch_dir,
    )
    outcome_check = blocked.checks.set_index("check").loc[
        "outcome_ledger_integrity"
    ]
    assert not blocked.passed
    assert not bool(outcome_check["passed"])
    assert blocked.summary.iloc[0]["next_gate"] == (
        "plan-research-family-launches"
    )


def test_research_family_launch_covers_bound_result_and_attested_abandonment(
    tmp_path,
):
    registration, registration_dir = _write_registration(tmp_path)
    registration_id = str(registration.summary.iloc[0]["registration_id"])
    pending = write_research_family_launch_matrix(
        registration_dir,
        output_dir=tmp_path / "launches",
    )
    leadlag_contract = pending.launches.set_index("study_label").loc["leadlag"]
    execution_receipt = write_research_family_launch_execution_receipt(
        load_research_family_launch_contract(
            tmp_path / "launches",
            str(leadlag_contract["contract_id"]),
        )
    )
    _write_bound_result(
        tmp_path / "results" / "leadlag",
        registration_dir=registration_dir,
        registration_id=registration_id,
        study_label="leadlag",
        launch_contract_id=str(leadlag_contract["contract_id"]),
        launch_contract_path=Path(str(leadlag_contract["contract_path"])),
        execution_receipt_path=execution_receipt.path,
        execution_receipt_id=execution_receipt.receipt_id,
    )
    abandonments = tmp_path / "abandonments.csv"
    pd.DataFrame(
        [{"study_label": "imbalance", "reason": "feed history was unavailable"}]
    ).to_csv(abandonments, index=False)

    report = write_research_family_launch_matrix(
        registration_dir,
        output_dir=tmp_path / "launches",
        abandonment_path=abandonments,
        attest_abandonments=True,
    )

    rows = report.launches.set_index("study_label")
    summary = report.summary.iloc[0]
    manifest = json.loads(
        (tmp_path / "launches" / "manifest.json").read_text(encoding="utf-8")
    )
    assert report.passed
    assert report.action_queue.empty
    assert rows.loc["leadlag", "study_status"] == "completed_ready"
    assert bool(rows.loc["leadlag", "result_manifest_current"])
    assert bool(rows.loc["leadlag", "result_registration_bound"])
    assert bool(rows.loc["leadlag", "result_launch_contract_bound"])
    assert rows.loc["imbalance", "study_status"] == "abandoned"
    assert bool(rows.loc["imbalance", "abandonment_valid"])
    assert rows["closure_covered"].astype(bool).all()
    assert int(summary["closure_covered_count"]) == 2
    assert summary["next_gate"] == "audit-research-family"
    assert manifest["run_type"] == "research_family_launch_matrix"
    assert manifest["inputs"]["research_family_abandonments"]["kind"] == "file"
    assert len(manifest["inputs"]["robust_study_manifests"]) == 1
    assert not manifest["extra"]["authorizes_submission"]
    family = write_research_family_audit(
        [tmp_path / "results" / "leadlag"],
        labels=["leadlag"],
        output_dir=tmp_path / "family",
        registration_path=registration_dir,
        launch_matrix_path=tmp_path / "launches",
        config=ResearchFamilyConfig(
            family_id="launch_matrix_family",
            declaration_complete_attested=True,
            require_prospective_registration=True,
            require_launch_coverage=True,
        ),
    )
    family_rows = family.studies.set_index("study_label")
    assert family.passed
    assert family_rows.loc["imbalance", "study_disposition"] == "abandoned"
    assert float(
        family_rows.loc["imbalance", "within_study_adjusted_pvalue"]
    ) == 1.0
    assert not bool(family_rows.loc["imbalance", "family_passed"])
    assert int(family.summary.iloc[0]["abandoned_study_count"]) == 1
    assert bool(family.summary.iloc[0]["launch_coverage_passed"])
    census = pd.read_csv(
        tmp_path / "family" / "research_family_launch_attempt_census.csv"
    )
    assert len(census) == 1
    assert census.iloc[0]["study_label"] == "leadlag"
    assert census.iloc[0]["outcome_status"] == "completed_ready"
    assert not bool(census.iloc[0]["is_operational_retry"])
    assert not bool(census.iloc[0]["counts_as_additional_hypothesis"])
    assert int(family.summary.iloc[0]["launch_attempt_count"]) == 1
    assert int(family.summary.iloc[0]["launch_outcome_count"]) == 1
    assert int(family.summary.iloc[0]["launch_operational_retry_count"]) == 0
    assert int(
        family.summary.iloc[0]["launch_additional_retry_hypothesis_count"]
    ) == 0
    family_cli_status = main(
        [
            "audit-research-family",
            "--studies",
            str(tmp_path / "results" / "leadlag"),
            "--label",
            "leadlag",
            "--out",
            str(tmp_path / "family_cli"),
            "--family-id",
            "launch_matrix_family",
            "--registration",
            str(registration_dir),
            "--require-prospective-registration",
            "--launch-matrix",
            str(tmp_path / "launches"),
            "--require-launch-coverage",
            "--attest-complete-family",
            "--fail-on-breach",
        ]
    )
    assert family_cli_status == 0
    catalog = catalog_experiment_runs([tmp_path / "launches"]).catalog.iloc[0]
    assert catalog["run_type"] == "research_family_launch_matrix"
    assert catalog["summary_file"] == "research_family_launch_summary.csv"
    assert bool(catalog["summary_status"])


def test_research_family_launch_cli_blocks_unattested_abandonment(tmp_path):
    _, registration_dir = _write_registration(tmp_path)
    abandonments = tmp_path / "abandonments.csv"
    pd.DataFrame(
        [{"study_label": "imbalance", "reason": "feed history was unavailable"}]
    ).to_csv(abandonments, index=False)
    output = tmp_path / "launches"

    status = main(
        [
            "plan-research-family-launches",
            "--registration",
            str(registration_dir),
            "--abandonments",
            str(abandonments),
            "--out",
            str(output),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(output / "research_family_launch_summary.csv").iloc[0]
    rows = pd.read_csv(output / "research_family_launch_matrix.csv").set_index(
        "study_label"
    )
    failed = set(
        pd.read_csv(output / "research_family_launch_checks.csv")
        .loc[lambda frame: ~frame["passed"].astype(bool), "check"]
    )
    assert status == 2
    assert not bool(summary["passed"])
    assert rows.loc["imbalance", "study_status"] == "never_launched"
    assert not bool(rows.loc["imbalance", "abandonment_valid"])
    assert "abandonments_attested" in failed


def test_research_family_launch_blocks_result_bound_to_different_registration(
    tmp_path,
):
    _, registration_dir = _write_registration(tmp_path)
    pending = write_research_family_launch_matrix(
        registration_dir,
        output_dir=tmp_path / "launches",
    )
    leadlag_contract = pending.launches.set_index("study_label").loc["leadlag"]
    execution_receipt = write_research_family_launch_execution_receipt(
        load_research_family_launch_contract(
            tmp_path / "launches",
            str(leadlag_contract["contract_id"]),
        )
    )
    _write_bound_result(
        tmp_path / "results" / "leadlag",
        registration_dir=registration_dir,
        registration_id="0" * 64,
        study_label="leadlag",
        launch_contract_id=str(leadlag_contract["contract_id"]),
        launch_contract_path=Path(str(leadlag_contract["contract_path"])),
        execution_receipt_path=execution_receipt.path,
        execution_receipt_id=execution_receipt.receipt_id,
    )
    abandonments = tmp_path / "abandonments.csv"
    pd.DataFrame(
        [{"study_label": "imbalance", "reason": "feed history was unavailable"}]
    ).to_csv(abandonments, index=False)

    report = write_research_family_launch_matrix(
        registration_dir,
        output_dir=tmp_path / "launches",
        abandonment_path=abandonments,
        attest_abandonments=True,
    )

    leadlag = report.launches.set_index("study_label").loc["leadlag"]
    assert not report.passed
    assert bool(leadlag["result_exists"])
    assert bool(leadlag["result_manifest_current"])
    assert not bool(leadlag["result_registration_bound"])
    assert not bool(leadlag["closure_covered"])
    assert "leadlag" in set(report.action_queue["component"])


def _write_registration(tmp_path):
    sweeps = _write_sweeps(tmp_path / "sweeps")
    plan_path = tmp_path / "plan.csv"
    pd.DataFrame(
        [
            {
                "study_label": label,
                "strategy": label,
                "market": "india_nse_index_derivatives",
                "hypothesis": f"{label} remains positive after costs",
                "planned_study_path": f"results/{label}",
                "primary_metric": "robust_score",
                "max_scenarios": 3,
                "development_sweeps": 6,
                "holdout_sweeps": 3,
                "sweep_paths_json": json.dumps([str(path) for path in sweeps]),
                "group_cols_json": json.dumps(["scenario"]),
                "sweep_labels_json": json.dumps(
                    [f"period_{index + 1}" for index in range(9)]
                ),
            }
            for label in ("leadlag", "imbalance")
        ]
    ).to_csv(plan_path, index=False)
    registration_dir = tmp_path / "registration"
    report = write_research_family_registration(
        plan_path,
        output_dir=registration_dir,
        family_id="launch_matrix_family",
    )
    return report, registration_dir


def _write_sweeps(root):
    paths = []
    source_dir = root / "_sources"
    source_dir.mkdir(parents=True)
    for index in range(9):
        path = root / f"period_{index + 1}"
        path.mkdir()
        pd.DataFrame(
            [
                {
                    "run": f"scenario_{scenario}",
                    "scenario": scenario,
                    "robust_score": score,
                    "net_pnl": score,
                    "proof_passed": True,
                    "max_drawdown": 0.0,
                    "fills": 10,
                    "worst_regime_equity_change": score,
                    "losing_regimes": 0,
                }
                for scenario, score in (("A", 10.0), ("B", 5.0), ("C", 1.0))
            ]
        ).to_csv(path / "sweep_runs.csv", index=False)
        source = source_dir / f"period_{index + 1}.csv"
        pd.DataFrame([{"ts": index, "bid": 100.0, "ask": 100.05}]).to_csv(
            source,
            index=False,
        )
        write_experiment_manifest(
            path,
            run_type="test_sweep",
            inputs={"market_data": source},
        )
        paths.append(path)
    return paths


def _write_bound_result(
    root,
    *,
    registration_dir,
    registration_id,
    study_label,
    launch_contract_id,
    launch_contract_path,
    execution_receipt_path,
    execution_receipt_id,
):
    root.mkdir(parents=True)
    significance_dir = root / "02_backtest_significance"
    overfit_dir = root / "02_backtest_overfit"
    significance_dir.mkdir()
    overfit_dir.mkdir()
    manifest_sha = file_sha256(registration_dir / "manifest.json")
    launch_contract_sha = file_sha256(launch_contract_path)
    execution_receipt_sha = file_sha256(execution_receipt_path)
    execution_receipt = load_research_family_launch_execution_receipt(
        execution_receipt_path
    )
    pd.DataFrame(
        [
            {
                "ready": True,
                "strategy": study_label,
                "market": "india_nse_index_derivatives",
                "candidate_scenario_key": f"scenario={study_label}",
                "overfit_scenario_count": 3,
                "development_sweep_count": 6,
                "holdout_sweep_count": 3,
                "adjusted_sign_pvalue": 0.01,
                "backtest_holdout_passed": True,
                "next_gate": "stage-orders",
                "research_registration_provided": True,
                "research_registration_passed": True,
                "research_registration_id": registration_id,
                "research_registration_manifest_sha256": manifest_sha,
                "registered_study_label": study_label,
                "research_launch_contract_provided": True,
                "research_launch_contract_passed": True,
                "research_launch_contract_id": launch_contract_id,
                "research_launch_contract_sha256": launch_contract_sha,
                "research_launch_execution_receipt_provided": True,
                "research_launch_execution_receipt_passed": True,
                "research_launch_execution_receipt_id": execution_receipt_id,
                "research_launch_execution_receipt_sha256": execution_receipt_sha,
                "research_launch_attempt_id": execution_receipt.attempt_id,
                "research_launch_attempt_number": execution_receipt.attempt_number,
                "research_launch_attempt_record_sha256": (
                    execution_receipt.attempt_record_sha256
                ),
                "authorizes_submission": False,
            }
        ]
    ).to_csv(root / "robust_selection_pipeline_summary.csv", index=False)
    pd.DataFrame(
        [
            {
                "passed": True,
                "registration_id": registration_id,
                "registered_study_label": study_label,
            }
        ]
    ).to_csv(
        root / "robust_selection_pipeline_research_registration.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {
                "passed": True,
                "contract_id": launch_contract_id,
                "contract_sha256": launch_contract_sha,
            }
        ]
    ).to_csv(
        root / "robust_selection_pipeline_research_launch_contract.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {
                "passed": True,
                "receipt_id": execution_receipt_id,
                "receipt_sha256": execution_receipt_sha,
            }
        ]
    ).to_csv(
        root / "robust_selection_pipeline_research_launch_execution_receipt.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {
                "passed": True,
                "candidate_scenario": f"scenario={study_label}",
                "scenario_trial_count": 3,
                "sign_pvalue": 0.003,
                "adjusted_sign_pvalue": 0.01,
            }
        ]
    ).to_csv(
        significance_dir / "backtest_significance_summary.csv",
        index=False,
    )
    pd.DataFrame(
        [{"passed": True, "score_column": "robust_score", "scenario_count": 3}]
    ).to_csv(overfit_dir / "backtest_overfit_summary.csv", index=False)
    write_experiment_manifest(
        root,
        run_type="robust_selection_pipeline",
        inputs={
            "research_family_registration": registration_dir,
            "research_family_registration_manifest": registration_dir
            / "manifest.json",
            "research_family_launch_contract": launch_contract_path,
            "research_family_launch_execution_receipt": execution_receipt_path,
            "research_family_launch_attempt_record": (
                execution_receipt.attempt_record_path
            ),
        },
    )
    write_research_family_launch_attempt_outcome(
        execution_receipt,
        exit_status=0,
        execution_completed=True,
    )
