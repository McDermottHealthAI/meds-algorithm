from datetime import datetime

import polars as pl
import pytest

from meds_algorithm.contracts.commands import STEP_SPECS, CommandName
from meds_algorithm.data.index import read_index, split_files
from meds_algorithm.spec import specification


def labelled_file(path, subject=1):
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {"subject_id": [subject], "prediction_time": [datetime(2020, 1, 1)], "boolean_value": [True]}
    ).write_parquet(path)
    return path


def test_index_reader_projects_keys_at_io_boundary(tmp_path, monkeypatch):
    labelled_file(tmp_path / "held_out.parquet")
    real_read = pl.read_parquet
    requested_columns = []

    def checked_read(path, **kwargs):
        requested_columns.append(kwargs.get("columns"))
        return real_read(path, **kwargs)

    monkeypatch.setattr(pl, "read_parquet", checked_read)
    index = read_index(tmp_path, ["held_out"])
    assert index.columns == ["subject_id", "prediction_time"]
    assert requested_columns == [["subject_id", "prediction_time"]]


def test_split_selection_rejects_partial_coverage_and_mislabelled_single_file(tmp_path):
    train = labelled_file(tmp_path / "train.parquet")
    with pytest.raises(FileNotFoundError, match="tuning"):
        split_files(tmp_path, ["train", "tuning"])
    with pytest.raises(FileNotFoundError, match="held_out"):
        split_files(train, ["held_out"])
    assert split_files(train, ["train"]) == [train]
    ambiguous = labelled_file(tmp_path / "arbitrary.parquet")
    with pytest.raises(FileNotFoundError):
        split_files(ambiguous, ["train"])
    shard = labelled_file(tmp_path / "held_out/0.parquet")
    assert split_files(shard, ["held_out"]) == [shard]


def test_index_reader_rejects_duplicate_and_missing_key_schemas(tmp_path):
    labelled_file(tmp_path / "train/0.parquet")
    labelled_file(tmp_path / "train/1.parquet")
    with pytest.raises(ValueError, match="duplicate"):
        read_index(tmp_path, ["train"])
    pl.DataFrame({"subject_id": [1]}).write_parquet(tmp_path / "held_out.parquet")
    with pytest.raises(ValueError, match="missing required key"):
        read_index(tmp_path, ["held_out"])


def test_roles_distinguish_ground_truth_from_prediction_keys():
    for name in (
        CommandName.infer_embeddings,
        CommandName.infer_trajectories,
        CommandName.predict_supervised,
        CommandName.predict_finetune,
        CommandName.predict_probe,
        CommandName.predict_zero_shot_direct,
        CommandName.predict_zero_shot_materialized,
    ):
        spec = STEP_SPECS[name]
        assert "external_index_dir" in spec.external_arguments
        assert "external_labels_dir" not in spec.external_arguments
        assert spec.label_access == "none"
    assert [i.argument for i in STEP_SPECS[CommandName.predict_probe].artifact_inputs] == [
        "input_embeddings_dir",
        "input_probe_algorithm_dir",
    ]
    for step in (CommandName.predict_supervised, CommandName.predict_finetune):
        assert "input_data_dir" in [i.argument for i in STEP_SPECS[step].artifact_inputs]


def test_specification_is_an_installed_package_resource():
    spec = specification()
    assert "# MEDS Algorithm Repository Contract, version 4" in spec
    assert "Ground-truth target values the algorithm may use" in spec
    assert "external_index_dir" in spec


def test_conflicting_split_names_never_select_evaluation_as_training(tmp_path):
    path = labelled_file(tmp_path / "train/held_out.parquet")
    with pytest.raises(ValueError, match="Ambiguous split"):
        split_files(tmp_path, ["train"])
    with pytest.raises(ValueError, match="Ambiguous split"):
        split_files(path, ["train"])
