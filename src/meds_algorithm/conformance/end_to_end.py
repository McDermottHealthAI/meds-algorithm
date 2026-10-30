"""Reusable end-to-end conformance; execution and fitted-feature inspection are algorithm-owned."""

from contextlib import suppress
from pathlib import Path

from meds_algorithm import (
    ALGORITHM_PROFILES,
    STEP_SPECS,
    ZERO_SHOT_TASK_COMMANDS,
    CommandName,
    RelaxationLedger,
    TaskSpec,
    read_manifest,
)

from .assertions import assert_prediction_keys, read_predictions


def _strip_labels(labels_dir: Path, destination: Path, splits) -> Path:
    """Remove outcomes from selected splits while retaining permitted training/context outcomes."""
    import polars as pl

    from meds_algorithm import split_files

    labels_dir = Path(labels_dir)
    files = split_files(labels_dir)
    stripped = set(files) if splits is None else set()
    for split in splits or ():
        # A separate training/context root need not contain any evaluated split.
        with suppress(FileNotFoundError):
            stripped.update(split_files(labels_dir, [split]))
    for path in split_files(labels_dir):
        target = destination / (path.relative_to(labels_dir) if Path(labels_dir).is_dir() else path.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        if path in stripped:
            pl.read_parquet(path, columns=["subject_id", "prediction_time"]).write_parquet(target)
        else:
            pl.read_parquet(path).write_parquet(target)
    return destination


def assert_profile_run(result, *, profile, run_e2e, fitted_codes, tmp_path):
    """Check actual artifacts, task binding, key coverage, prediction reads and split canaries."""
    artifacts = result.artifacts
    assert list(artifacts) == [command.value for command in ALGORITHM_PROFILES[profile]]
    for command, directory in artifacts.items():
        manifest = read_manifest(directory)
        assert manifest["command"]["name"] == command
        assert manifest["artifact"]["type"] == STEP_SPECS[CommandName(command)].artifact_type.value
        assert str(manifest["command"]["config_digest"]).startswith("sha256:"), (
            f"{command} has no config digest"
        )
        resources = manifest["resources"]
        assert resources["wall_seconds"] >= 0
        memory = resources["memory"]
        if memory["source"] == "unavailable":
            assert memory["peak_process_tree_rss_bytes"] is None
        else:
            assert memory["peak_process_tree_rss_bytes"] > 0
    prediction_step = ALGORITHM_PROFILES[profile][-1].value
    read_predictions(artifacts[prediction_step])
    prediction_manifest = read_manifest(artifacts[prediction_step])
    assert prediction_manifest["artifact"]["type"] == "predictions"
    assert_prediction_keys(artifacts[prediction_step], result.labels_dir, result.splits)

    assert_label_blind_pipeline(result, profile=profile, run_e2e=run_e2e, tmp_path=tmp_path)

    # Absence of transductive fitting (SPEC 2.1): codes that occur only in tuning or held-out subjects must
    # not be part of anything the algorithm fitted.
    assert set(result.canaries) == {"tuning", "held_out"}, (
        "run_e2e must apply core conformance.signal.add_split_canaries and return the canaries"
    )
    leaked = set(result.canaries.values()) & set(fitted_codes(artifacts))
    assert not leaked, f"statistics were fitted over non-training splits: {sorted(leaked)}"

    # Zero-shot: every task-conditioned artifact names its task, and a ledger is published (SPEC 2.4, 3.1).
    if not profile.startswith("zero_shot_"):
        return
    task = TaskSpec.from_arguments(result.inputs)
    for command in ZERO_SHOT_TASK_COMMANDS.get(profile, ()):
        manifest = read_manifest(artifacts[command.value])
        assert manifest["semantics_digest"] == task.semantics_digest(), (
            f"{command.value} is not bound to the task"
        )
        assert manifest["inputs"]["task"]["criteria_file"]["digest"].startswith("sha256:")
    ledgers = [path.parent for d in artifacts.values() for path in Path(d).rglob("relaxations.yaml")]
    assert ledgers, "every zero-shot run must publish relaxations.yaml"
    for directory in ledgers:
        RelaxationLedger.read(directory)  # raises unless query_language, decoded_quantity, and exact are set


def assert_label_blind_pipeline(result, *, profile, run_e2e, tmp_path):
    """Rerun every stage on the same histories with forbidden outcomes absent and fresh artifacts."""
    assert result.inputs.get("external_meds_dir"), "E2EResult.inputs must record external_meds_dir"
    assert type(result.inputs.get("seed")) is int, "E2EResult.inputs must record the run_e2e seed"
    expected_steps = [step.value for step in ALGORITHM_PROFILES[profile]]
    original = read_predictions(result.artifacts[expected_steps[-1]])
    overrides = dict(result.inputs)
    for argument in ("external_labels_dir", "external_index_dir", "external_evaluation_labels_dir"):
        overrides[argument] = _strip_labels(
            result.inputs.get(argument) or result.labels_dir,
            tmp_path / "unlabelled-inputs" / argument,
            None if profile.startswith("zero_shot_") else result.splits,
        )
    fresh_root = tmp_path / "label-blind-run"
    blind = run_e2e(
        fresh_root,
        profile=profile,
        **{
            **overrides,
            "splits": result.splits,
        },
    )
    assert list(blind.artifacts) == expected_steps, "label-blind check must execute the full lifecycle"
    old_paths = {Path(path).resolve() for path in result.artifacts.values()}
    for step, path in blind.artifacts.items():
        path = Path(path).resolve()
        assert path not in old_paths and path.is_relative_to(fresh_root.resolve()), (
            "label-blind check must publish fresh outputs inside its run directory"
        )
        manifest = read_manifest(path)
        assert manifest["command"]["name"] == step
        assert manifest["artifact"]["type"] == STEP_SPECS[CommandName(step)].artifact_type.value
    prediction = blind.artifacts[expected_steps[-1]]
    assert_prediction_keys(prediction, result.labels_dir, result.splits)
    # Do not require the evaluation-only boolean_value on a deliberately unlabelled run.
    import polars as pl
    from polars.testing import assert_frame_equal

    from ..data.index import read_index
    from ..evaluation.predictions import check_decoded

    blind_predictions = read_predictions(prediction, require_truth=False)
    check_decoded(read_index(result.labels_dir, result.splits), blind_predictions)
    columns = ["subject_id", "prediction_time", "predicted_boolean_probability"]
    if "predicted_boolean_value" in original.columns:
        columns.append("predicted_boolean_value")
    try:
        assert_frame_equal(
            original.select(columns).sort(columns[:2]),
            blind_predictions.select(columns).sort(columns[:2]),
            check_exact=False,
            rel_tol=1e-6,
            abs_tol=1e-8,
        )
    except (AssertionError, pl.exceptions.ColumnNotFoundError) as error:
        raise AssertionError(
            "Predictions changed when forbidden labels were removed; fix leakage or make the "
            "conformance fixture reproducible with the recorded seed"
        ) from error
