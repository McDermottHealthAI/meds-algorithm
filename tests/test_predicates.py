from dataclasses import dataclass, replace
from datetime import datetime

import polars as pl
import pytest
import yaml

from meds_algorithm import (
    AlgorithmConfig,
    ArtifactDestination,
    PayloadMetadata,
    PredictOnlyAlgorithm,
    StepRunner,
    TaskSpec,
)
from meds_algorithm.artifacts.manifest import digest_file
from meds_algorithm.data.predicates import compose_feature_predicates
from meds_algorithm.requests import PredictionIndex, PredictOnlyRequest, PreprocessDataRequest


class Reader(PredictOnlyAlgorithm):
    name = "reader"

    def validate_inputs(self, request):
        if isinstance(request, PreprocessDataRequest):
            assert "extra" in yaml.safe_load(request.predicates_file.read_text())["predicates"]

    def preprocess_data(self, request):
        assert "extra" in yaml.safe_load(request.predicates_file.read_text())["predicates"]
        return PayloadMetadata("fixture")

    def predict_only(self, request):
        assert set(yaml.safe_load(request.predicates_file.read_text())["predicates"]) == {"base"}
        assert request.task.predicates_file == request.predicates_file
        request.index.read().with_columns(pl.lit(0.5).alias("predicted_boolean_probability")).write_parquet(
            request.output.directory / "predictions.parquet"
        )
        return PayloadMetadata("fixture")


def setup(tmp_path):
    meds = tmp_path / "meds"
    meds.mkdir()
    base = tmp_path / "base.yaml"
    base.write_text("predicates:\n  base: {code: BASE}\n")
    extra = tmp_path / "extra.yaml"
    extra.write_text("predicates:\n  extra: {expr: 'or(base, base)'}\n")
    config_path = tmp_path / "config.yaml"
    config_path.write_text("additional_predicates_file: extra.yaml\n")
    config = AlgorithmConfig.from_file(config_path)
    request = PreprocessDataRequest(
        meds_dir=meds, predicates_file=base, output=ArtifactDestination(tmp_path / "data")
    )
    return config, request, base, extra


def test_resolved_features_are_saved_and_do_not_change_task_predicates(tmp_path):
    config, request, base, extra = setup(tmp_path)
    assert config.additional_predicates_file == extra.resolve()
    runner = StepRunner()
    artifact = runner.run(Reader(config), "preprocess_data", request, profile="predict_only")
    resolved = artifact.directory / "resolved_feature_predicates.yaml"
    assert set(yaml.safe_load(resolved.read_text())["predicates"]) == {"base", "extra"}
    sources = artifact.read_manifest()["inputs"]["feature_predicates"]
    assert sources["base"]["digest"] == digest_file(base)
    assert sources["additional"]["digest"] == digest_file(extra)
    assert sources["resolved"] == {"path": resolved.name, "digest": digest_file(resolved)}
    assert PreprocessDataRequest.load(artifact.directory / "request.json") == request
    assert AlgorithmConfig.load(artifact.directory / "config.json") == config
    extra.unlink()  # Later stages use persisted features and never reopen the temporary additions.
    task_file = tmp_path / "task.yaml"
    task_file.write_text("description: fixture\n")
    pl.DataFrame({"subject_id": [1], "prediction_time": [datetime(2020, 1, 1)]}).write_parquet(
        tmp_path / "held_out.parquet"
    )
    task = TaskSpec(task_file, base)
    prediction = PredictOnlyRequest(
        data=artifact,
        index=PredictionIndex(tmp_path, ("held_out",)),
        task=task,
        predicates_file=base,
        output=ArtifactDestination(tmp_path.parent / f"{tmp_path.name}-predictions"),
    )
    result = runner.run(Reader(config), "predict_only", prediction, profile="predict_only")
    assert "feature_predicates" not in result.read_manifest()["inputs"]
    assert result.read_manifest()["semantics_digest"] == task.semantics_digest()


@pytest.mark.parametrize(
    "content",
    [
        "predicates:\n  base: {code: BASE}\n",  # Even identical definitions collide.
        "predicates:\n  extra: {code: A}\n  extra: {code: B}\n",
        "predicates:\n  extra: {code: A, code: B}\n",
        "predicates: {}\ntrigger: extra\n",
        "predicates: [extra]\n",
        "predicates: {extra: null}\n",
    ],
)
def test_invalid_extensions_never_call_algorithm_or_publish(tmp_path, content):
    config, request, _, extra = setup(tmp_path)
    extra.write_text(content)
    with pytest.raises(ValueError):
        StepRunner().run(Reader(config), "preprocess_data", request, profile="predict_only")
    assert not request.output.directory.exists()


def test_additions_without_base_and_required_config_fields(tmp_path):
    @dataclass(frozen=True)
    class Required(AlgorithmConfig):
        width: int

    assert Required(3).width == 3  # Shared optional field does not constrain subclass field ordering.
    _, _, _, extra = setup(tmp_path)
    content, sources = compose_feature_predicates(None, extra)
    assert sources["base"] is None
    assert set(yaml.safe_load(content)["predicates"]) == {"extra"}


def test_predicate_change_changes_digest_and_modified_resolution_rolls_back(tmp_path):
    config, request, base, extra = setup(tmp_path)
    runner = StepRunner()
    original = runner.run(Reader(config), "preprocess_data", request, profile="predict_only")
    old_manifest = (original.directory / "manifest.yaml").read_bytes()
    extra.write_text("predicates:\n  extra: {code: CHANGED}\n")
    changed = runner.run(
        Reader(config),
        "preprocess_data",
        replace(request, output=ArtifactDestination(tmp_path / "changed")),
        profile="predict_only",
    )
    assert (
        original.read_manifest()["command"]["config_digest"]
        != changed.read_manifest()["command"]["config_digest"]
    )

    class Modifier(Reader):
        def preprocess_data(self, request):
            request.predicates_file.write_text("predicates: {}\n")
            return PayloadMetadata("fixture")

    with pytest.raises(ValueError, match="modified"):
        runner.run(
            Modifier(config),
            "preprocess_data",
            replace(request, execution=replace(request.execution, overwrite=True)),
            profile="predict_only",
        )
    assert (original.directory / "manifest.yaml").read_bytes() == old_manifest
    assert yaml.safe_load(base.read_text()) == {"predicates": {"base": {"code": "BASE"}}}
