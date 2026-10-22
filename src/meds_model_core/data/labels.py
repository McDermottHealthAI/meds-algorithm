"""Explicit training/context targets and strict split-scoped outcome reads."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from .index import read_index, split_files
from .validation import INDEX_COLUMNS, validate_keys, validate_splits

if TYPE_CHECKING:
    import polars as pl


def read_targets(root: Path | str, splits: Sequence[str], *, allow_unlabelled=False) -> pl.DataFrame | None:
    import polars as pl

    validate_splits(splits)
    files = split_files(root, splits)
    schemas = [pl.read_parquet_schema(path) for path in files]
    if any(not all(key in schema for key in INDEX_COLUMNS) for schema in schemas):
        raise ValueError("target files are missing required key columns")
    labelled = ["boolean_value" in schema for schema in schemas]
    if not any(labelled) and allow_unlabelled:
        read_index(root, splits)
        return None
    if not all(labelled):
        raise ValueError("every selected target file must contain boolean_value; mixed schemas are invalid")
    frame = pl.concat([pl.read_parquet(path, columns=[*INDEX_COLUMNS, "boolean_value"]) for path in files])
    validate_keys(frame, source="targets")
    if frame["boolean_value"].dtype != pl.Boolean or frame["boolean_value"].null_count():
        raise ValueError("boolean_value must contain non-null Boolean outcomes")
    return frame


def read_context_labels(
    labels_dir: Path | str, context_splits: Sequence[str], evaluated_splits: Sequence[str]
) -> pl.DataFrame:
    """Read disjoint labelled context; neither split names nor keys may overlap evaluation."""
    validate_splits(context_splits)
    validate_splits(evaluated_splits)
    if set(context_splits) & set(evaluated_splits):
        raise ValueError("context splits must be disjoint from evaluated splits")
    context = read_targets(labels_dir, context_splits)
    evaluated = read_index(labels_dir, evaluated_splits)
    if context.select(INDEX_COLUMNS).join(evaluated, on=list(INDEX_COLUMNS), how="inner").height:
        raise ValueError("context keys must be disjoint from evaluated keys")
    return context
