"""Keyed probabilities and post-score ground-truth attachment."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from ..data.labels import read_targets
from ..data.validation import INDEX_COLUMNS, validate_keys

if TYPE_CHECKING:
    import polars as pl
PREDICTED_PROBABILITY = "predicted_boolean_probability"


def check_decoded(index: pl.DataFrame, predictions: pl.DataFrame) -> pl.DataFrame:
    """Require unique, non-null matching keys and finite probabilities in [0, 1]."""
    import polars as pl

    validate_keys(index, source="requested index")
    validate_keys(predictions, source="decoded predictions")
    keys = list(INDEX_COLUMNS)
    missing = index.select(keys).join(predictions.select(keys), on=keys, how="anti")
    extra = predictions.select(keys).join(index.select(keys), on=keys, how="anti")
    if missing.height or extra.height:
        raise ValueError(f"decoded predictions miss {missing.height} and add {extra.height} requested keys")
    if PREDICTED_PROBABILITY not in predictions.columns:
        raise ValueError(f"decoded predictions lack {PREDICTED_PROBABILITY}")
    values = predictions[PREDICTED_PROBABILITY]
    if (
        values.dtype not in (pl.Float32, pl.Float64)
        or values.null_count()
        or not values.is_finite().all()
        or not values.is_between(0.0, 1.0).all()
    ):
        raise ValueError(f"{PREDICTED_PROBABILITY} must be a finite non-null probability in [0, 1]")
    return predictions


def attach_ground_truth(
    predictions: pl.DataFrame, labels_dir: Path | str, splits: Sequence[str]
) -> pl.DataFrame:
    """Join truth only after scores are fixed; an entirely unlabelled index is supported.

    This function cannot enforce when the caller scores. Its result must never feed back into
    preprocessing, algorithm fitting, selection or scoring. Missing splits/mixed label schemas fail.
    """
    validate_keys(predictions, source="predictions")
    labels = read_targets(labels_dir, splits, allow_unlabelled=True)
    if labels is None:
        return predictions
    joined = predictions.drop("boolean_value", strict=False).join(labels, on=list(INDEX_COLUMNS), how="left")
    if joined.height != predictions.height or joined["boolean_value"].null_count():
        raise ValueError("every prediction key must have exactly one ground-truth label")
    return joined
