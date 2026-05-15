from argparse import Namespace

from experiments import run_f4_structure_matcher_audit as worker


class FakeMatcher:
    def fit(self, candidate, reference) -> bool:
        return candidate == reference


def _args() -> Namespace:
    return Namespace(
        ltol=0.2,
        stol=0.3,
        angle_tol=5.0,
        confidence_match=0.95,
        confidence_no_match=0.75,
        confidence_no_bucket=0.0,
    )


def _reference(reference_id: str, formula: str, structure: str) -> dict:
    return {
        "reference_id": reference_id,
        "reference_source": "alex20_train_snapshot",
        "formula": formula,
        "structure": structure,
    }


def test_f4_worker_control_gate_passes_positive_and_no_bucket_controls() -> None:
    reference_buckets = {
        "BaTiO3": [_reference("alex-1", "BaTiO3", "structure-1")],
        "SrTiO3": [_reference("alex-2", "SrTiO3", "structure-2")],
    }
    control_tasks, setup_issues = worker._build_control_tasks(
        reference_buckets,
        positive_control_count=1,
        include_no_bucket_control=True,
        reference_pool_id="reference_pool_v1",
    )

    results = [
        worker._audit_task(
            task,
            matcher=FakeMatcher(),
            reference_buckets=reference_buckets,
            reference_pool_id="reference_pool_v1",
            audit_run_id="audit-1",
            args=_args(),
        )
        for task in control_tasks
    ]
    gate = worker._control_gate(control_tasks, results, setup_issues)

    assert setup_issues == []
    assert gate["status"] == "passed"
    assert gate["positive_control_count"] == 1
    assert gate["positive_control_pass_count"] == 1
    assert gate["no_bucket_control_count"] == 1
    assert gate["no_bucket_control_pass_count"] == 1
    assert len(gate["control_set_sha256"]) == 64
    positive = next(row for row in results if row["candidate_id"].startswith("__f4_positive_control__"))
    assert positive["f4_novelty_leakage"] == 1.0
    assert positive["nearest_reference_id"] == "alex-1"
    no_bucket = next(row for row in results if row["candidate_id"] == "__f4_no_exact_formula_bucket_control__")
    assert no_bucket["match_type"] == "no_exact_formula_reference"
    assert no_bucket["confidence"] == 0.0
    assert no_bucket["metadata"]["interpretation"] == "coverage_gap_not_low_risk_evidence"


def test_f4_worker_control_gate_fails_when_positive_controls_are_missing() -> None:
    reference_buckets = {"BaTiO3": [_reference("alex-1", "BaTiO3", "structure-1")]}
    control_tasks, setup_issues = worker._build_control_tasks(
        reference_buckets,
        positive_control_count=2,
        include_no_bucket_control=False,
        reference_pool_id="reference_pool_v1",
    )
    results = [
        worker._audit_task(
            task,
            matcher=FakeMatcher(),
            reference_buckets=reference_buckets,
            reference_pool_id="reference_pool_v1",
            audit_run_id="audit-1",
            args=_args(),
        )
        for task in control_tasks
    ]

    gate = worker._control_gate(control_tasks, results, setup_issues)

    assert gate["status"] == "failed"
    assert gate["positive_control_count"] == 1
    assert gate["positive_control_pass_count"] == 1
    assert gate["failure_count"] == 1
    assert gate["failures"][0]["actual"] == "positive_control_shortfall:expected_2:actual_1"
