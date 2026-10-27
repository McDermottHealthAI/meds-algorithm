"""Strict split selection and key-only projection. Requires the optional data extra."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from .validation import INDEX_COLUMNS, validate_keys, validate_splits


def split_files(root: Path | str, splits: Sequence[str] | None = None) -> list[Path]:
    """Select every requested split or fail; never broaden a missing split to all files."""
    root = Path(root)
    if isinstance(splits, str):
        raise TypeError("splits must be a sequence, not a string")
    if splits is not None:
        validate_splits(splits)
    candidates = sorted(root.rglob("*.parquet")) if root.is_dir() else [root]
    candidates = [p for p in candidates if p.is_file() and p.suffix == ".parquet"]
    if not candidates:
        raise FileNotFoundError(f"No parquet index files under {root}")
    split_names = {"train", "tuning", "held_out", *(splits or ())}
    for path in candidates:
        parts = path.relative_to(root).parts[:-1] if root.is_dir() else (root.parent.name,)
        identities = {path.stem, *parts, *([root.name] if root.is_dir() else [])} & split_names
        if len(identities) > 1:
            raise ValueError(f"Ambiguous split identity for {path}: {sorted(identities)}")
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
    """Project keys at the Parquet read, never loading label columns into the algorithm boundary."""
    import polars as pl

    frames = []
    for path in split_files(root, splits):
        schema = pl.read_parquet_schema(path)
        if not all(column in schema for column in INDEX_COLUMNS):
            raise ValueError(f"Index file {path} is missing required key columns")
        frames.append(pl.read_parquet(path, columns=list(INDEX_COLUMNS)))
    index = pl.concat(frames)
    validate_keys(index, source="requested index")
    return index
