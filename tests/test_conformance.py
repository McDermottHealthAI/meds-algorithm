from datetime import datetime
from pathlib import Path

import polars as pl
import pytest

from meds_model_core import (
    MODEL_PROFILES,
    STEP_SPECS,
    RelaxationLedger,
    TaskSpec,
    attach_ground_truth,
    digest_config,
    measured_artifact,
    read_index,
)
from meds_model_core.conformance.end_to_end import assert_label_blind_pipeline, assert_profile_run
from meds_model_core.conformance.types import E2EResult


@pytest.fixture
def pipeline(tmp_path):
    labels = tmp_path / "labels"
    labels.mkdir()
    for split, subject in (("train", 1), ("tuning", 2), ("held_out", 3)):
        pl.DataFrame(
            {"subject_id": [subject], "prediction_time": [datetime(2020, 1, 1)], "boolean_value": [True]}
        ).write_parquet(labels / f"{split}.parquet")
    criteria = tmp_path / "task.yaml"
    criteria.write_text("task: synthetic\n")
    histories = tmp_path / "meds"
    histories.mkdir()

    def run(path, *, profile, **overrides):
        inputs = {
            "external_meds_dir": histories,
            "external_task_criteria_file": criteria,
            "external_labels_dir": labels,
            **overrides,
        }
        index_dir = inputs.get("external_index_dir", inputs["external_labels_dir"])
        splits = inputs.get("splits", ["held_out"])
        task = TaskSpec(criteria)
        artifacts = {}
        for step in MODEL_PROFILES[profile]:
            spec = STEP_SPECS[step]
            dest = Path(path) / step.value
            with measured_artifact(
                dest,
                artifact_type=spec.artifact_type.value,
                command=step.value,
                producer="conformance-fixture",
                payload_format="test/v1",
                config_digest=digest_config({}),
                inputs={"task": task.provenance()} if spec.task_conditioned else None,
                semantics_digest=task.semantics_digest() if spec.task_conditioned else None,
            ) as staging:
                if step == MODEL_PROFILES[profile][-1]:
                    predicted = read_index(index_dir, splits).with_columns(
                        pl.lit(0.5).alias("predicted_boolean_probability")
                    )
                    attach_ground_truth(
                        predicted, inputs.get("external_evaluation_labels_dir", index_dir), splits
                    ).write_parquet(staging / "predictions.parquet")
                    if spec.task_conditioned:
                        RelaxationLedger("fixture", "synthetic", True).write(staging)
            artifacts[step.value] = dest
        return E2EResult(
            artifacts,
            index_dir,
            splits,
            inputs,
            canaries={"tuning": "CANARY//tuning", "held_out": "CANARY//held_out"},
        )

    return run


@pytest.mark.parametrize("profile", list(MODEL_PROFILES))
def test_shared_conformance_runs_each_profile_from_fresh_outputs(tmp_path, pipeline, profile):
    result = pipeline(tmp_path / "original", profile=profile)
    assert_profile_run(
        result,
        profile=profile,
        run_e2e=pipeline,
        fitted_codes=lambda artifacts: set(),
        tmp_path=tmp_path / "checks",
    )


def test_full_lifecycle_check_catches_labels_read_before_prediction(tmp_path, pipeline):
    result = pipeline(tmp_path / "original", profile="supervised")

    def leaky_preprocessing(path, *, profile, **inputs):
        pl.read_parquet(Path(inputs["external_labels_dir"]) / "held_out.parquet", columns=["boolean_value"])
        return pipeline(path, profile=profile, **inputs)

    with pytest.raises(pl.exceptions.ColumnNotFoundError):
        assert_label_blind_pipeline(
            result, profile="supervised", run_e2e=leaky_preprocessing, tmp_path=tmp_path / "checks"
        )


def test_full_lifecycle_check_rejects_cached_outputs(tmp_path, pipeline):
    result = pipeline(tmp_path / "original", profile="probe")
    with pytest.raises(AssertionError, match="fresh outputs"):
        assert_label_blind_pipeline(
            result, profile="probe", run_e2e=lambda *args, **kwargs: result, tmp_path=tmp_path / "checks"
        )
