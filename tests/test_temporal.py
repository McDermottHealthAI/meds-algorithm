"""Temporal-leakage conformance: null world, future perturbation and the chance-level test."""

import math
import random
from pathlib import Path

import polars as pl
import pytest

from meds_algorithm import (
    ALGORITHM_PROFILES,
    STEP_SPECS,
    attach_ground_truth,
    digest_config,
    measured_artifact,
    read_index,
)
from meds_algorithm.conformance.temporal import (
    FUTURE_BLIND_ATOL,
    FUTURE_BLIND_RTOL,
    NULL_WORLD_DATASET,
    assert_chance_level,
    assert_future_blind_pipeline,
    assert_same_predictions,
    build_null_world_dataset,
    null_auroc_test,
    perturb_future,
)
from meds_algorithm.conformance.types import E2EResult


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    return build_null_world_dataset(
        tmp_path_factory.mktemp("null") / "world", n_train=60, n_tuning=20, n_held_out=400, seed=3
    )


def _events(meds_dir, split="held_out"):
    return pl.concat(pl.read_parquet(p) for p in sorted((Path(meds_dir) / "data" / split).glob("*.parquet")))


def _keyed_gap(meds_dir, index, *, future: bool):
    """Hours since the last event at or before T (causal) or until the first event after T (leaky)."""
    events = _events(meds_dir).filter(pl.col("time").is_not_null() & (pl.col("code") != "MEDS_BIRTH"))
    joined = index.join(events.select("subject_id", "time"), on="subject_id", how="left")
    if future:
        picked = (
            joined.filter(pl.col("time") > pl.col("prediction_time"))
            .group_by("subject_id", "prediction_time")
            .agg(pl.col("time").min())
        )
        gap = pl.col("time") - pl.col("prediction_time")
    else:
        picked = (
            joined.filter(pl.col("time") <= pl.col("prediction_time"))
            .group_by("subject_id", "prediction_time")
            .agg(pl.col("time").max())
        )
        gap = pl.col("prediction_time") - pl.col("time")
    hours = picked.with_columns((gap.dt.total_microseconds() / 3.6e9).alias("hours"))
    return index.join(
        hours.select("subject_id", "prediction_time", "hours"),
        on=["subject_id", "prediction_time"],
        how="left",
    ).with_columns(pl.col("hours").fill_null(1e3))


def toy_pipeline(*, leaky: bool):
    """A supervised 'algorithm' whose score is a time gap: causal, or the NOAH-style gap to the next event."""

    def run(path, *, profile, **inputs):
        inputs = {"seed": 0, **inputs}
        index_dir = inputs.get("external_index_dir") or inputs["external_labels_dir"]
        splits = list(inputs.get("splits") or ["held_out"])
        artifacts = {}
        for step in ALGORITHM_PROFILES[profile]:
            dest = Path(path) / step.value
            with measured_artifact(
                dest,
                artifact_type=STEP_SPECS[step].artifact_type.value,
                command=step.value,
                producer="toy",
                payload_format="test/v1",
                config_digest=digest_config({}),
            ) as out:
                if step == ALGORITHM_PROFILES[profile][-1]:
                    index = read_index(index_dir, splits)
                    gap = _keyed_gap(inputs["external_meds_dir"], index, future=leaky)
                    # Short gap to the next event -> high score (a leaky model would learn exactly this).
                    scored = gap.with_columns(
                        (1 / (1 + pl.col("hours"))).alias("predicted_boolean_probability")
                    )
                    attach_ground_truth(
                        scored.drop("hours"), inputs.get("external_evaluation_labels_dir", index_dir), splits
                    ).write_parquet(out / "predictions.parquet")
            artifacts[step.value] = dest
        return E2EResult(artifacts, Path(index_dir), splits, inputs, canaries={})

    return run


def _run(world, tmp_path, *, leaky):
    return toy_pipeline(leaky=leaky)(
        tmp_path / "run",
        profile="supervised",
        external_meds_dir=world.meds_dir,
        external_labels_dir=world.labels_dir,
        splits=["held_out"],
    )


def test_null_world_shape(world):
    held_out = pl.read_parquet(world.labels_dir / "held_out.parquet")
    train = pl.read_parquet(world.labels_dir / "train.parquet")
    assert held_out["subject_id"].n_unique() == held_out.height == 400
    assert train.height == 2 * 60
    assert 0.4 < held_out["boolean_value"].mean() < 0.6
    assert '"dataset_name": "null_world"' in (world.meds_dir / "metadata" / "dataset.json").read_text()
    assert NULL_WORLD_DATASET == "null_world"
    events = _events(world.meds_dir)
    last_t = held_out.group_by("subject_id").agg(pl.col("prediction_time").max())
    # Every record continues well past its prediction time, so the end of a record carries no information.
    end = events.group_by("subject_id").agg(pl.col("time").max()).join(last_t, on="subject_id")
    assert (end["time"] > end["prediction_time"] + world.horizon).mean() > 0.95


def test_causal_scores_are_at_chance_and_leaky_scores_are_caught(world, tmp_path):
    auroc, p = assert_chance_level(_run(world, tmp_path / "causal", leaky=False))
    assert abs(auroc - 0.5) < 0.1 and p >= 1e-3
    with pytest.raises(AssertionError, match="null world"):
        assert_chance_level(_run(world, tmp_path / "leaky", leaky=True))


def test_perturbation_keeps_history_and_rewrites_only_indexed_futures(world, tmp_path):
    index = read_index(world.labels_dir, ["held_out"])
    perturbed = perturb_future(world.meds_dir, world.labels_dir, tmp_path / "perturbed", splits=["held_out"])
    before, after = _events(world.meds_dir), _events(perturbed)
    cut = pl.col("time").is_null() | (pl.col("time") <= pl.col("prediction_time"))
    past = [
        frame.join(index, on="subject_id")
        .filter(cut)
        .drop("prediction_time")
        .sort("subject_id", "time", "code", nulls_last=False)
        for frame in (before, after)
    ]
    assert past[0].equals(past[1])
    assert not before.equals(after)
    assert set(after["code"].unique()) <= set(before["code"].unique())
    # Subjects outside the index (training) are untouched.
    assert _events(world.meds_dir, "train").equals(_events(perturbed, "train"))


def test_future_blind_rerun_passes_causal_and_fails_leaky(world, tmp_path):
    causal = toy_pipeline(leaky=False)
    result = _run(world, tmp_path / "causal", leaky=False)
    assert_future_blind_pipeline(result, profile="supervised", run_e2e=causal, tmp_path=tmp_path / "c")
    leaky = toy_pipeline(leaky=True)
    result = _run(world, tmp_path / "leaky", leaky=True)
    with pytest.raises(AssertionError, match="after every indexed prediction time"):
        assert_future_blind_pipeline(result, profile="supervised", run_e2e=leaky, tmp_path=tmp_path / "l")


def test_mann_whitney_is_calibrated_and_handles_ties():
    rng = random.Random(0)
    rejections = 0
    for _ in range(400):
        labels = [rng.random() < 0.5 for _ in range(200)]
        scores = [round(rng.random(), 1) for _ in labels]  # heavy ties
        rejections += null_auroc_test(scores, labels)[1] < 0.05
    assert 0.02 < rejections / 400 < 0.08
    assert null_auroc_test([0.5] * 10, [True, False] * 5) == (0.5, 1.0)
    auroc, p = null_auroc_test(list(range(100)), [i >= 50 for i in range(100)])
    assert auroc == 1.0 and p < 1e-12
    with pytest.raises(ValueError, match="both positive and negative"):
        null_auroc_test([0.1, 0.2], [True, True])
    assert math.isclose(null_auroc_test([0.2, 0.8, 0.4, 0.6], [False, True, True, False])[0], 0.75)


def test_perturbation_keeps_tie_order_and_never_copies_objects(tmp_path):
    from datetime import datetime, timedelta

    t0 = datetime(2020, 1, 1)
    # Ties at one time, in a deliberately non-alphabetical row order, plus an object-link row.
    rows = [(1, t0, c, None, None) for c in ("Z//LAST", "A//FIRST", "M//MIDDLE")]
    rows += [
        (1, t0 + timedelta(hours=1), "ECG//WAVEFORM", None, "ecg/1"),
        (1, t0 + timedelta(hours=9), "X", 1.0, None),
    ]
    schema = {
        "subject_id": pl.Int64,
        "time": pl.Datetime("us"),
        "code": pl.String,
        "numeric_value": pl.Float32,
        "ecg_link": pl.String,
    }
    meds, labels = tmp_path / "meds", tmp_path / "labels"
    (meds / "data" / "held_out").mkdir(parents=True)
    pl.DataFrame(rows, schema=schema, orient="row").write_parquet(meds / "data" / "held_out" / "0.parquet")
    labels.mkdir()
    pl.DataFrame(
        {"subject_id": [1], "prediction_time": [t0 + timedelta(hours=2)], "boolean_value": [True]},
        schema={"subject_id": pl.Int64, "prediction_time": pl.Datetime("us"), "boolean_value": pl.Boolean},
    ).write_parquet(labels / "held_out.parquet")
    for seed in range(5):
        out = perturb_future(meds, labels, tmp_path / f"p{seed}", splits=["held_out"], seed=seed)
        after = pl.read_parquet(out / "data" / "held_out" / "0.parquet")
        assert after["code"].head(4).to_list() == ["Z//LAST", "A//FIRST", "M//MIDDLE", "ECG//WAVEFORM"]
        assert after.filter(pl.col("ecg_link").is_not_null()).height == 1
        future = after.slice(4)  # the old future (X) is gone; 8 new plain rows after T replace it
        assert future.height == 8 and (future["time"] > t0 + timedelta(hours=2)).all()
        assert set(future["code"]) <= {"Z//LAST", "A//FIRST", "M//MIDDLE", "X"}


def test_future_blind_tolerance_absorbs_rounding_but_not_leaks():
    """A leak-free polars score moved by one unit in the last place on a CI runner; a leak moves far more."""
    keys = {"subject_id": [1, 2], "prediction_time": [0, 0]}
    original = pl.DataFrame({**keys, "predicted_boolean_probability": [0.5, 1e-3]})
    rounded = pl.DataFrame({**keys, "predicted_boolean_probability": [math.nextafter(0.5, 1), 1e-3]})
    leaked = pl.DataFrame({**keys, "predicted_boolean_probability": [0.5 + 1e-9, 1e-3]})
    check = {"rtol": FUTURE_BLIND_RTOL, "atol": FUTURE_BLIND_ATOL, "message": "moved"}
    assert_same_predictions(original, rounded, **check)
    with pytest.raises(AssertionError, match="1 of 2 keys moved"):
        assert_same_predictions(original, leaked, **check)
