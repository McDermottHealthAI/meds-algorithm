from datetime import datetime
from pathlib import Path

import polars as pl
import pytest

from meds_algorithm import (
    ALGORITHM_PROFILES,
    STEP_SPECS,
    RelaxationLedger,
    TaskSpec,
    attach_ground_truth,
    digest_config,
    measured_artifact,
    read_index,
)
from meds_algorithm.conformance.end_to_end import assert_label_blind_pipeline, assert_profile_run
from meds_algorithm.conformance.types import E2EResult


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
            "seed": 0,
            "external_meds_dir": histories,
            "external_task_criteria_file": criteria,
            "external_labels_dir": labels,
            **overrides,
        }
        index_dir = inputs.get("external_index_dir", inputs["external_labels_dir"])
        splits = inputs.get("splits", ["held_out"])
        task = TaskSpec(criteria)
        artifacts = {}
        for step in ALGORITHM_PROFILES[profile]:
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
                if step == ALGORITHM_PROFILES[profile][-1]:
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


def check(result, runner, tmp_path):
    assert_profile_run(
        result, profile="supervised", run_e2e=runner, fitted_codes=lambda _: set(), tmp_path=tmp_path
    )


def test_optional_label_leakage_changes_scores_and_fails(tmp_path, pipeline):
    def leaky(path, *, profile, **inputs):
        result = pipeline(path, profile=profile, **inputs)
        labels = pl.read_parquet(result.labels_dir / "held_out.parquet")
        value = (
            labels["boolean_value"].cast(pl.Float64)
            if "boolean_value" in labels.columns
            else pl.Series([0.25])
        )
        output = result.artifacts["predict_supervised"] / "predictions.parquet"
        pl.read_parquet(output).with_columns(value.alias("predicted_boolean_probability")).write_parquet(
            output
        )
        return result

    result = leaky(tmp_path / "original", profile="supervised")
    with pytest.raises(AssertionError, match="Predictions changed"):
        check(result, leaky, tmp_path / "checks")


@pytest.mark.parametrize("probability", [float("nan"), float("inf"), -0.1, 1.1])
def test_original_invalid_scores_fail_before_rerun(tmp_path, pipeline, probability):
    result = pipeline(tmp_path / "original", profile="supervised")
    output = result.artifacts["predict_supervised"] / "predictions.parquet"
    pl.read_parquet(output).with_columns(
        pl.lit(probability).alias("predicted_boolean_probability")
    ).write_parquet(output)
    with pytest.raises(ValueError, match="probability"):
        check(result, lambda *a, **kw: pytest.fail("must reject original first"), tmp_path / "checks")


def test_sharded_predictions_and_separate_training_roots(tmp_path, pipeline):
    import shutil

    from meds_algorithm.data.labels import read_targets

    initial = pipeline(tmp_path / "setup", profile="supervised")
    training, index = tmp_path / "training", tmp_path / "index"
    training.mkdir()
    index.mkdir()
    for split in ("train", "tuning"):
        shutil.copy2(initial.labels_dir / f"{split}.parquet", training / f"{split}.parquet")
    shutil.copy2(initial.labels_dir / "held_out.parquet", index / "held_out.parquet")

    def separated(path, *, profile, **inputs):
        inputs = {
            "external_labels_dir": training,
            "external_index_dir": index,
            "external_evaluation_labels_dir": index,
            **inputs,
        }
        targets = read_targets(inputs["external_labels_dir"], ["train", "tuning"])
        assert targets["boolean_value"].to_list() == [True, True]
        result = pipeline(path, profile=profile, **inputs)
        output = result.artifacts["predict_supervised"]
        (output / "held_out").mkdir()
        (output / "predictions.parquet").rename(output / "held_out/0.parquet")
        return result

    check(separated(tmp_path / "original", profile="supervised"), separated, tmp_path / "checks")


def test_reproducible_seed_is_required(tmp_path, pipeline):
    result = pipeline(tmp_path / "original", profile="supervised")
    result.inputs.pop("seed")
    with pytest.raises(AssertionError, match="seed"):
        check(result, pipeline, tmp_path / "checks")


@pytest.mark.parametrize("profile", list(ALGORITHM_PROFILES))
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
