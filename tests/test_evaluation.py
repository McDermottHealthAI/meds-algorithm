from datetime import datetime

import polars as pl
import pytest

from meds_model_core import attach_ground_truth, check_decoded, read_context_labels
from meds_model_core.conformance.assertions import assert_prediction_keys


def frame(subject=1, labelled=True):
    value = {"subject_id": [subject], "prediction_time": [datetime(2020, 1, 1)]}
    if labelled:
        value["boolean_value"] = [True]
    return pl.DataFrame(value)


def test_truth_join_selects_each_split_and_preserves_scores(tmp_path):
    frame().write_parquet(tmp_path / "held_out.parquet")
    frame(2).write_parquet(tmp_path / "train.parquet")
    prediction = frame(labelled=False).with_columns(pl.lit(0.25).alias("predicted_boolean_probability"))
    actual = attach_ground_truth(prediction, tmp_path, ["held_out"])
    assert actual["predicted_boolean_probability"].to_list() == [0.25]
    with pytest.raises(FileNotFoundError):
        attach_ground_truth(prediction, tmp_path, ["held_out", "tuning"])
    with pytest.raises(FileNotFoundError):
        attach_ground_truth(prediction, tmp_path / "train.parquet", ["held_out"])


def test_mixed_missing_or_duplicated_labels_fail(tmp_path):
    prediction = frame(labelled=False)
    frame().write_parquet(tmp_path / "held_out.parquet")
    frame(2, labelled=False).write_parquet(tmp_path / "tuning.parquet")
    with pytest.raises(ValueError, match="mixed"):
        attach_ground_truth(prediction, tmp_path, ["held_out", "tuning"])
    pl.concat([frame(), frame()]).write_parquet(tmp_path / "held_out.parquet")
    with pytest.raises(ValueError, match="duplicate"):
        attach_ground_truth(prediction, tmp_path, ["held_out"])


def test_context_cannot_overlap_evaluated_keys_under_another_split_name(tmp_path):
    frame().write_parquet(tmp_path / "train.parquet")
    frame(labelled=False).write_parquet(tmp_path / "held_out.parquet")
    with pytest.raises(ValueError, match="disjoint"):
        read_context_labels(tmp_path, ["train"], ["held_out"])
    with pytest.raises(ValueError, match="splits"):
        read_context_labels(tmp_path, ["train"], "held_out")


@pytest.mark.parametrize("probability", [float("nan"), float("inf"), -0.1, 1.1, None])
def test_decoded_rejects_invalid_probabilities(probability):
    index = frame(labelled=False)
    predictions = index.with_columns(
        pl.lit(probability, dtype=pl.Float64).alias("predicted_boolean_probability")
    )
    with pytest.raises(ValueError, match="probability"):
        check_decoded(index, predictions)


def test_conformance_never_broadens_missing_splits(tmp_path):
    labels = tmp_path / "labels"
    predictions = tmp_path / "predictions"
    labels.mkdir()
    predictions.mkdir()
    frame().write_parquet(labels / "train.parquet")
    frame().with_columns(pl.lit(0.5).alias("predicted_boolean_probability")).write_parquet(
        predictions / "predictions.parquet"
    )
    with pytest.raises(FileNotFoundError):
        assert_prediction_keys(predictions, labels, ["held_out"])
