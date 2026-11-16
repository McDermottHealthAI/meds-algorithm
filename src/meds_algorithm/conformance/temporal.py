"""Temporal-leakage checks: nothing recorded after a prediction time may reach that time's prediction.

Two complementary, algorithm-agnostic checks run through the algorithm's own ``run_e2e`` adapter:

* **Future perturbation (deterministic).** :func:`perturb_future` copies a MEDS dataset, deletes every event
  after each evaluated subject's latest prediction time and adds random events there instead. Inputs at every
  indexed prediction time are unchanged, so a leak-free pipeline must reproduce its predictions exactly
  (:func:`assert_future_blind_pipeline`). This catches any path from the future to a prediction, including a
  path the fitted model barely uses, and needs no statistical threshold.
* **Null world (statistical).** :func:`build_null_world_dataset` writes a dataset whose future is
  independent of its past: every subject's events follow one homogeneous Poisson process (the same rate for
  everyone), with codes and values drawn independently, and records continue well past every prediction
  time. The label, "does any event occur in (T, T + horizon]", depends only on the future, so held-out
  discrimination must be at chance. :func:`assert_chance_level` applies a one-sided Mann-Whitney test with
  one key per held-out subject, so its false-positive rate is exactly ``alpha``. A leak only shows up here
  if training learned to use it; read this check as an end-to-end smoke alarm and the perturbation check as
  the gate.
"""

from __future__ import annotations

import json
import math
import random
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

US_PER_HOUR = 3_600_000_000
NULL_WORLD_DATASET = "null_world"
# (code, share of events, numeric mean, numeric sd); a None mean gives an event without a value.
NULL_WORLD_CODES: tuple[tuple[str, float, float | None, float | None], ...] = (
    ("NULL//MEASUREMENT//A", 0.30, 80.0, 12.0),
    ("NULL//MEASUREMENT//B", 0.20, 96.0, 2.0),
    ("NULL//MEASUREMENT//C", 0.20, 1.0, 0.3),
    ("NULL//EVENT//D", 0.15, None, None),
    ("NULL//EVENT//E", 0.15, None, None),
)


@dataclass(frozen=True)
class NullWorld:
    """Paths of a written null-world dataset and the label it defines."""

    meds_dir: Path
    labels_dir: Path
    horizon: timedelta
    rate_per_hour: float


def build_null_world_dataset(
    root: Path,
    *,
    n_train: int = 400,
    n_tuning: int = 100,
    n_held_out: int = 1000,
    rate_per_hour: float = 0.5,
    keys_per_train_subject: int = 2,
    history_hours: tuple[float, float] = (12.0, 36.0),
    tail_hours: float = 48.0,
    codes: tuple[tuple[str, float, float | None, float | None], ...] = NULL_WORLD_CODES,
    dataset_name: str = NULL_WORLD_DATASET,
    seed: int = 0,
) -> NullWorld:
    """Write ``root/meds`` (MEDS 0.4) and ``root/labels`` for a world in which the future is unpredictable.

    Each subject has a ``MEDS_BIRTH`` event, a static sex code and Poisson events at ``rate_per_hour``.
    Prediction times are drawn uniformly in ``history_hours`` after the first possible event, independently
    of the events, and every record runs ``tail_hours`` past its last prediction time, so record ends carry
    no information. The label is whether any event occurs in ``(T, T + horizon]`` with
    ``horizon = ln 2 / rate`` (prevalence 0.5 in expectation). Training subjects contribute
    ``keys_per_train_subject`` keys; tuning and held-out subjects one each, so held-out keys are independent.
    Pass ``codes`` when an algorithm needs a fixed vocabulary.
    """
    import polars as pl

    if not codes or abs(sum(share for _, share, *_ in codes) - 1) > 1e-9:
        raise ValueError("codes must be non-empty and their shares must sum to 1")
    root = Path(root)
    meds_dir, labels_dir = root / "meds", root / "labels"
    rng = random.Random(seed)
    names = [code for code, *_ in codes]
    shares = [share for _, share, *_ in codes]
    horizon_us = int(math.log(2) / rate_per_hour * US_PER_HOUR)
    epoch = datetime(2100, 1, 1)
    event_schema = {
        "subject_id": pl.Int64,
        "time": pl.Datetime("us"),
        "code": pl.String,
        "numeric_value": pl.Float32,
    }
    label_schema = {"subject_id": pl.Int64, "prediction_time": pl.Datetime("us"), "boolean_value": pl.Boolean}

    def at(microseconds: int) -> datetime:
        return epoch + timedelta(microseconds=microseconds)

    subject_id, subject_splits = 0, []
    labels_dir.mkdir(parents=True, exist_ok=True)
    for split, size in (("train", n_train), ("tuning", n_tuning), ("held_out", n_held_out)):
        events, labels = [], []
        for _ in range(size):
            subject_id += 1
            start = rng.randrange(3 * 365 * 24) * US_PER_HOUR
            n_keys = keys_per_train_subject if split == "train" else 1
            offsets = sorted(rng.uniform(*history_hours) for _ in range(n_keys))
            end_hours = offsets[-1] + tail_hours
            times, t = [], rng.expovariate(rate_per_hour)
            while t < end_hours:
                times.append(start + int(t * US_PER_HOUR))
                t += rng.expovariate(rate_per_hour)
            birth = start - int(rng.uniform(20, 90) * 365.25 * 24 * US_PER_HOUR)
            events.append((subject_id, at(birth), "MEDS_BIRTH", None))
            events.append((subject_id, None, f"SEX//{rng.choice('FM')}", None))
            for time in times:
                code, _, mean, sd = codes[rng.choices(range(len(codes)), weights=shares)[0]]
                events.append((subject_id, at(time), code, None if mean is None else rng.gauss(mean, sd)))
            for offset in offsets:
                prediction = start + int(offset * US_PER_HOUR)
                label = any(prediction < time <= prediction + horizon_us for time in times)
                labels.append((subject_id, at(prediction), label))
            subject_splits.append((subject_id, split))
        (meds_dir / "data" / split).mkdir(parents=True, exist_ok=True)
        pl.DataFrame(events, schema=event_schema, orient="row").sort(
            "subject_id", "time", nulls_last=False
        ).write_parquet(meds_dir / "data" / split / "0.parquet")
        pl.DataFrame(labels, schema=label_schema, orient="row").write_parquet(labels_dir / f"{split}.parquet")
    metadata = meds_dir / "metadata"
    metadata.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"code": [*names, "MEDS_BIRTH", "SEX//F", "SEX//M"]}).write_parquet(
        metadata / "codes.parquet"
    )
    pl.DataFrame(
        subject_splits, schema={"subject_id": pl.Int64, "split": pl.String}, orient="row"
    ).write_parquet(metadata / "subject_splits.parquet")
    (metadata / "dataset.json").write_text(json.dumps({"dataset_name": dataset_name, "meds_version": "0.4"}))
    return NullWorld(meds_dir, labels_dir, timedelta(microseconds=horizon_us), rate_per_hour)


def perturb_future(
    meds_dir: Path,
    index_dir: Path,
    destination: Path,
    *,
    splits=None,
    events_per_subject: int = 8,
    span: timedelta = timedelta(hours=48),
    seed: int = 0,
) -> Path:
    """Copy ``meds_dir`` to ``destination`` and rewrite every indexed subject's future.

    For each subject in the index (restricted to ``splits``), every timed event strictly after the subject's
    latest indexed prediction time is deleted and ``events_per_subject`` new events are added at
    log-uniformly random offsets in ``(T, T + span]`` (from one microsecond on, so leaks that look only a
    little past ``T`` are exercised). New events copy the code, numeric value and text value of random
    timed rows of the same shard, so they use the split's own vocabulary. Rows carrying any other column
    (object links and other additional value modalities) are never copied: each object is one acquisition,
    and linking it a second time would fabricate an impossible record. Events at or before every indexed
    time are untouched and keep their row order (MEDS ties at one time are ordered by row), so every
    indexed prediction must stay exactly the same. Training subjects outside the index are not changed.
    """
    import polars as pl

    from ..data.index import read_index

    destination = Path(destination)
    shutil.copytree(meds_dir, destination)
    latest = (
        read_index(index_dir, splits).group_by("subject_id").agg(pl.col("prediction_time").max().alias("_T"))
    )
    rng = random.Random(seed)
    for shard in sorted((destination / "data").rglob("*.parquet")):
        events = pl.read_parquet(shard)
        # Joins do not promise row order; the row index restores it, since tie order at one time matters.
        tagged = events.with_row_index("_row").join(latest, on="subject_id", how="left").sort("_row")
        future = pl.col("_T").is_not_null() & pl.col("time").is_not_null() & (pl.col("time") > pl.col("_T"))
        subjects = (
            tagged.filter(pl.col("_T").is_not_null()).select("subject_id", "_T").unique().sort("subject_id")
        )
        plain = [
            c
            for c in events.columns
            if c not in ("subject_id", "time", "code", "numeric_value", "text_value")
        ]
        pool = events.filter(
            pl.col("time").is_not_null()
            & ~pl.col("code").str.starts_with("MEDS_")
            & pl.all_horizontal([pl.col(c).is_null() for c in plain] or [pl.lit(True)])
        )
        if subjects.is_empty():
            continue
        kept = tagged.filter(~future).select(events.columns)
        n = subjects.height * events_per_subject if pool.height else 0
        span_us = int(span.total_seconds() * 1_000_000)
        # Log-uniform: many events land just after T (where binning or rounding leaks peek), some far later.
        offsets = [max(1, int(math.exp(rng.uniform(0, math.log(span_us))))) for _ in range(n)]
        new = (
            pool.sample(n, with_replacement=True, seed=rng.randrange(2**32))
            .with_columns(
                pl.Series(
                    "subject_id",
                    subjects["subject_id"].to_list() * events_per_subject,
                    dtype=events.schema["subject_id"],
                ),
                (
                    pl.Series("_T", subjects["_T"].to_list() * events_per_subject).cast(pl.Datetime("us"))
                    + pl.duration(microseconds=pl.Series(offsets))
                )
                .cast(events.schema["time"])
                .alias("time"),
            )
            .select(events.columns)
        )
        # Stable: rows at or before T keep their order; new rows sit at unique times after T.
        pl.concat([kept, new]).sort(
            "subject_id", "time", nulls_last=False, maintain_order=True
        ).write_parquet(shard)
    return destination


def null_auroc_test(scores, labels) -> tuple[float, float]:
    """AUROC and its one-sided Mann-Whitney p-value against chance (ties averaged, continuity corrected).

    Valid when keys are independent and the scores were fixed before ``labels`` were attached.
    """
    import polars as pl

    frame = pl.DataFrame({"score": list(scores), "label": [bool(v) for v in labels]})
    positives = int(frame["label"].sum())
    negatives = frame.height - positives
    if not positives or not negatives:
        raise ValueError("the null-world held-out split needs both positive and negative keys")
    frame = frame.with_columns(pl.col("score").rank("average").alias("rank"))
    u = float(frame.filter(pl.col("label"))["rank"].sum()) - positives * (positives + 1) / 2
    n = frame.height
    ties = frame.group_by("score").len()["len"].cast(pl.Float64)
    variance = positives * negatives / 12 * ((n + 1) - float((ties**3 - ties).sum()) / (n * (n - 1)))
    auroc = u / (positives * negatives)
    if variance <= 0:
        return auroc, 1.0
    z = (u - positives * negatives / 2 - 0.5) / math.sqrt(variance)
    return auroc, 0.5 * math.erfc(z / math.sqrt(2))


def assert_chance_level(result, *, alpha: float = 1e-3) -> tuple[float, float]:
    """Fail when held-out predictions on a null world discriminate the future better than chance."""
    import polars as pl

    from meds_algorithm import split_files

    from .assertions import read_predictions

    step = list(result.artifacts)[-1]
    assert step.startswith("predict"), f"the last artifact must hold predictions, got {step}"
    keys = ["subject_id", "prediction_time"]
    predictions = read_predictions(result.artifacts[step], require_truth=False).select(
        *keys, "predicted_boolean_probability"
    )
    truth = pl.concat(
        pl.read_parquet(p, columns=[*keys, "boolean_value"])
        for p in split_files(result.labels_dir, result.splits)
    )
    joined = truth.join(predictions, on=keys, how="inner")
    assert joined.height == truth.height, "every null-world key needs a prediction"
    assert joined["subject_id"].n_unique() == joined.height, "the null-world test needs one key per subject"
    auroc, p_value = null_auroc_test(joined["predicted_boolean_probability"], joined["boolean_value"])
    assert p_value >= alpha, (
        f"Held-out AUROC {auroc:.3f} on a null world where the future is independent of the past "
        f"(one-sided p = {p_value:.2e} < {alpha}). Information from after the prediction time reaches the "
        "prediction; run the future-perturbation check to locate it."
    )
    return auroc, p_value


def assert_same_predictions(original, other, *, message: str, rtol: float = 1e-6, atol: float = 1e-8) -> None:
    """Keyed equality of probabilities (and decisions, when present) within ``atol + rtol * |p|``."""
    import polars as pl

    keys = ["subject_id", "prediction_time"]
    probability = "predicted_boolean_probability"
    decisions = "predicted_boolean_value" in original.columns
    columns = [*keys, probability, *(["predicted_boolean_value"] if decisions else [])]
    # Explicit comparison instead of polars.testing.assert_frame_equal, whose tolerance keywords were
    # renamed (rtol/atol -> rel_tol/abs_tol) within the supported polars>=1 range.
    try:
        a = original.select(columns).sort(keys)
        b = other.select(columns).sort(keys)
    except pl.exceptions.ColumnNotFoundError as error:
        raise AssertionError(f"{message}: predictions lack a column of the original run") from error
    if not a.select(keys).equals(b.select(keys)):
        raise AssertionError(f"{message}: prediction keys differ")
    moved = (a[probability] - b[probability]).abs() > atol + rtol * b[probability].abs()
    if moved.any() or (decisions and not a["predicted_boolean_value"].equals(b["predicted_boolean_value"])):
        raise AssertionError(
            f"{message} ({int(moved.sum())} of {a.height} keys moved, max |change| "
            f"{float((a[probability] - b[probability]).abs().max()):.3g})"
        )


def assert_future_blind_pipeline(result, *, profile, run_e2e, tmp_path, tolerance: float = 0.0) -> None:
    """Rerun every stage with each evaluated subject's future rewritten; predictions must not move.

    Training data, seeds and the inputs at every indexed time are identical in both runs, so a deterministic
    pipeline reproduces its predictions bit for bit; the default ``tolerance`` is therefore zero. A small
    leak through a briefly trained conformance model can move a probability by only ~1e-7, which a float
    tolerance would hide. Pass a relative ``tolerance`` only for a pipeline that is not bitwise reproducible.
    """
    from meds_algorithm import ALGORITHM_PROFILES

    from .assertions import assert_prediction_keys, read_predictions

    assert result.inputs.get("external_meds_dir"), "E2EResult.inputs must record external_meds_dir"
    assert type(result.inputs.get("seed")) is int, "E2EResult.inputs must record the run_e2e seed"
    steps = [step.value for step in ALGORITHM_PROFILES[profile]]
    index = result.inputs.get("external_index_dir") or result.labels_dir
    perturbed = perturb_future(
        result.inputs["external_meds_dir"],
        index,
        Path(tmp_path) / "future-perturbed-meds",
        splits=result.splits,
        seed=result.inputs["seed"] + 1,
    )
    fresh_root = Path(tmp_path) / "future-blind-run"
    rerun = run_e2e(
        fresh_root,
        profile=profile,
        **{**result.inputs, "external_meds_dir": perturbed, "splits": result.splits},
    )
    assert list(rerun.artifacts) == steps, "future-blind check must execute the full lifecycle"
    for path in rerun.artifacts.values():
        assert Path(path).resolve().is_relative_to(fresh_root.resolve()), (
            "future-blind check must publish fresh outputs inside its run directory"
        )
    prediction = rerun.artifacts[steps[-1]]
    assert_prediction_keys(prediction, result.labels_dir, result.splits)
    assert_same_predictions(
        read_predictions(result.artifacts[steps[-1]], require_truth=False),
        read_predictions(prediction, require_truth=False),
        rtol=tolerance,
        atol=0.0,
        message="Predictions changed when only events after every indexed prediction time were rewritten; "
        "information from after the prediction time reaches the prediction",
    )
