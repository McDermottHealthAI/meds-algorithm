"""Strict split selection and key-only projection. Requires the optional data extra."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

INDEX_COLUMNS = ("subject_id", "prediction_time")


def split_files(root: Path | str, splits: Sequence[str] | None = None) -> list[Path]:
    """Select every requested split or fail; never broaden a missing split to all files."""
    root = Path(root)
    if isinstance(splits, str):
        raise TypeError("splits must be a sequence, not a string")
    if splits is not None and (
        not splits
        or any(not isinstance(s, str) or not s.strip() for s in splits)
        or len(set(splits)) != len(splits)
    ):
        raise ValueError("splits must be a nonempty sequence of unique names")
    candidates = sorted(root.rglob("*.parquet")) if root.is_dir() else [root]
    candidates = [p for p in candidates if p.is_file() and p.suffix == ".parquet"]
    if not candidates:
        raise FileNotFoundError(f"No parquet index files under {root}")
    if splits is None:
        return candidates
    selected: set[Path] = set()
    for split in splits:
        matches = []
        for path in candidates:
            # A single file must also prove which split it represents; its unrelated ancestors do not.
            parts = path.relative_to(root).parts[:-1] if root.is_dir() else (root.parent.name,)
            if path.stem == split or split in parts or (root.is_dir() and root.name == split):
                matches.append(path)
        if not matches:
            raise FileNotFoundError(f"No parquet files for requested split {split!r} under {root}")
        selected.update(matches)
    return sorted(selected)


def read_index(root: Path | str, splits: Sequence[str] | None = None):
    """Project keys at the Parquet read, never loading label columns into the model boundary."""
    import polars as pl

    frames = []
    for path in split_files(root, splits):
        schema = pl.read_parquet_schema(path)
        if not all(column in schema for column in INDEX_COLUMNS):
            raise ValueError(f"Index file {path} is missing required key columns")
        frames.append(pl.read_parquet(path, columns=list(INDEX_COLUMNS)))
    index = pl.concat(frames)
    if any(index[column].null_count() for column in INDEX_COLUMNS):
        raise ValueError("the requested index contains null keys")
    if index.unique().height != index.height:
        raise ValueError("the requested index contains duplicate (subject_id, prediction_time)")
    return index
