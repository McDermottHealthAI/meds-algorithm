"""Shared key and split validation without importing a dataframe engine at module import."""

from collections.abc import Sequence

INDEX_COLUMNS = ("subject_id", "prediction_time")


def validate_splits(splits: Sequence[str]) -> None:
    if (
        isinstance(splits, str)
        or not isinstance(splits, Sequence)
        or not splits
        or any(not isinstance(s, str) or not s.strip() for s in splits)
        or len(set(splits)) != len(splits)
    ):
        raise ValueError("splits must be a nonempty sequence of unique nonblank names")


def validate_keys(frame, *, source="index") -> None:
    if not all(column in frame.columns for column in INDEX_COLUMNS):
        raise ValueError(f"{source} is missing required key columns")
    if any(frame[column].null_count() for column in INDEX_COLUMNS):
        raise ValueError(f"{source} contains null keys")
    if frame.select(INDEX_COLUMNS).unique().height != frame.height:
        raise ValueError(f"{source} contains duplicate keys")
