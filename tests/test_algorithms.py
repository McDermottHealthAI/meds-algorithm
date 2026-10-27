"""Public runner tests, strict config round trips and restartable profile execution."""

import os
import subprocess
import sys
from dataclasses import FrozenInstanceError, dataclass, field, replace
from datetime import datetime
from pathlib import Path

import polars as pl
import pytest

from meds_model_core import (
    AlgorithmRepository,
    ArtifactDestination,
    ExecutionOptions,
    FinetuneAlgorithm,
    ModelConfig,
    PayloadMetadata,
    PredictOnlyAlgorithm,
    ProbeAlgorithm,
    StepRunner,
    SupervisedAlgorithm,
    ZeroShotDirectAlgorithm,
    ZeroShotMaterializedAlgorithm,
    read_manifest,
)
from meds_model_core.algorithms import profile_classes, request_type
from meds_model_core.requests import (
    PredictionIndex,
    PredictSupervisedRequest,
    PreprocessDataRequest,
    TrainingLabels,
    TrainSupervisedRequest,
)


@dataclass(frozen=True)
class FeatureConfig(ModelConfig):
    format: str = "toy"


@dataclass(frozen=True)
class ToyConfig(ModelConfig):
    features: FeatureConfig = field(default_factory=FeatureConfig)
    iterations: int = 10

    def validate(self):
        if self.iterations < 1:
            raise ValueError("iterations must be positive")


class ToyAlgorithm(SupervisedAlgorithm):
    name = "toy"
    config_type = ToyConfig

    def preprocess_data(self, request):
        (request.output.directory / "features.txt").write_text("toy")
        return PayloadMetadata("toy-data")

    def train_supervised(self, request):
        probability = request.labels.read()["boolean_value"].mean()
        (request.output.directory / "probability.txt").write_text(str(probability))
        return PayloadMetadata("toy-model")

    def predict_supervised(self, request):
        probability = float((request.model.directory / "probability.txt").read_text())
        frame = request.index.read().with_columns(pl.lit(probability).alias("predicted_boolean_probability"))
        frame.write_parquet(request.output.directory / "predictions.parquet")
        return PayloadMetadata("toy-predictions")


@pytest.fixture
def prepared(tmp_path):
    meds = tmp_path / "meds"
    meds.mkdir()
    labels = tmp_path / "labels"
    labels.mkdir()
    for split, ids, outcomes in (("train", [1, 2], [False, True]), ("held_out", [3, 4], [True, False])):
        pl.DataFrame(
            {"subject_id": ids, "prediction_time": [datetime(2020, 1, 1)] * 2, "boolean_value": outcomes}
        ).write_parquet(labels / f"{split}.parquet")
    runner = StepRunner()
    data = runner.run(
        ToyAlgorithm(),
        "preprocess_data",
        PreprocessDataRequest(meds_dir=meds, output=ArtifactDestination(tmp_path / "data")),
        profile="supervised",
    )
    model = runner.run(
        ToyAlgorithm(),
        "train_supervised",
        TrainSupervisedRequest(
            data=data, labels=TrainingLabels(labels), output=ArtifactDestination(tmp_path / "model")
        ),
        profile="supervised",
    )
    request = PredictSupervisedRequest(
        data=data,
        model=model,
        index=PredictionIndex(labels, ("held_out",)),
        output=ArtifactDestination(tmp_path / "predictions"),
    )
    return runner, request


def test_configuration_is_strict_immutable_and_roundtrips(tmp_path):
    config = ToyConfig.from_dict({"features": {"format": "other"}})
    assert config.iterations == 10
    with pytest.raises(FrozenInstanceError):
        config.iterations = 1
    for values in ({"unknown": 1}, {"iterations": True}, {"iterations": "10"}, {"iterations": 0}):
        with pytest.raises((TypeError, ValueError)):
            ToyConfig.from_dict(values)
    path = config.save(tmp_path / "config.json")
    assert ToyConfig.load(path) == config
    with pytest.raises(ValueError, match="type or schema"):
        ModelConfig.load(path)


def test_runner_publishes_resolved_config_and_request(prepared):
    runner, request = prepared
    result = runner.run(
        ToyAlgorithm(),
        "predict_supervised",
        request,
        profile="supervised",
        evaluation_labels_dir=request.index.directory,
    )
    manifest = result.read_manifest()
    assert manifest["algorithm"]["config"] == ToyConfig().to_dict()
    assert manifest["inputs"]["input_supervised_model_dir"]["manifest_digest"].startswith("sha256:")
    assert manifest["inputs"]["external_index_dir"]["keys_digest"].startswith("sha256:")
    assert manifest["invocation"]["request"]["output"]["directory"] == str(result.directory)
    assert PredictSupervisedRequest.load(result.directory / "request.json") == request
    assert ToyConfig.load(result.directory / "config.json") == ToyConfig()
    assert "boolean_value" in pl.read_parquet(result.directory / "predictions.parquet").columns


def test_reloaded_request_runs_in_a_fresh_process(prepared, tmp_path):
    runner, request = prepared
    original = runner.run(ToyAlgorithm(), "predict_supervised", request, profile="supervised")
    reloaded = replace(request, output=ArtifactDestination(tmp_path / "fresh"))
    reloaded.save(tmp_path / "request.json")
    ToyConfig().save(tmp_path / "config.json")
    script = """
import sys
from pathlib import Path
from test_algorithms import ToyAlgorithm, ToyConfig
from meds_model_core import StepRunner
from meds_model_core.requests import PredictSupervisedRequest
root = Path(sys.argv[1])
StepRunner().run(ToyAlgorithm(ToyConfig.load(root / 'config.json')), 'predict_supervised',
    PredictSupervisedRequest.load(root / 'request.json'), profile='supervised')
"""
    subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        check=True,
        env={**os.environ, "PYTHONPATH": os.pathsep.join([str(Path(__file__).parent), *sys.path])},
        capture_output=True,
        text=True,
    )
    assert pl.read_parquet(original.directory / "predictions.parquet").equals(
        pl.read_parquet(tmp_path / "fresh/predictions.parquet")
    )


def test_runner_validates_before_model_and_preserves_previous_output(prepared):
    runner, request = prepared
    with pytest.raises(ValueError, match="configuration mismatch"):
        runner.run(
            ToyAlgorithm(ToyConfig(iterations=20)), "predict_supervised", request, profile="supervised"
        )
    assert not request.output.directory.exists()
    runner.run(ToyAlgorithm(), "predict_supervised", request, profile="supervised")
    old = (request.output.directory / "manifest.yaml").read_bytes()

    class Broken(ToyAlgorithm):
        def predict_supervised(self, request):
            request.index.read().with_columns(
                pl.lit(float("nan")).alias("predicted_boolean_probability")
            ).write_parquet(request.output.directory / "bad.parquet")
            return PayloadMetadata("broken")

    with pytest.raises(ValueError, match="probability"):
        runner.run(
            Broken(),
            "predict_supervised",
            replace(request, execution=ExecutionOptions(overwrite=True)),
            profile="supervised",
        )
    assert (request.output.directory / "manifest.yaml").read_bytes() == old
    assert not list(request.output.directory.parent.glob(".predictions.staging-*"))


def test_request_types_and_paths_cannot_cross_boundaries(prepared):
    runner, request = prepared
    with pytest.raises(TypeError, match="requires"):
        runner.run(ToyAlgorithm(), "train_supervised", request, profile="supervised")
    with pytest.raises(ValueError, match="overlap"):
        runner.run(
            ToyAlgorithm(),
            "predict_supervised",
            replace(request, output=ArtifactDestination(request.data.directory)),
            profile="supervised",
        )
    arguments = {
        "input_data_dir": str(request.data.directory),
        "input_supervised_model_dir": str(request.model.directory),
        "external_index_dir": str(request.index.directory),
        "splits": ["held_out"],
        "output_predictions_dir": str(request.output.directory),
    }
    for bad in ({"external_labels_dir": "/forbidden"}, {"spilts": ["train"]}, {"seed": True}, {"splits": []}):
        with pytest.raises((TypeError, ValueError)):
            PredictSupervisedRequest.from_arguments({**arguments, **bad})
    repository = AlgorithmRepository({"supervised": ToyAlgorithm})
    result = repository.run("predict_supervised", arguments)
    assert result.directory == request.output.directory


def test_profile_requests_are_the_source_of_legacy_metadata():
    from meds_model_core import MODEL_PROFILES, STEP_SPECS

    for profile in profile_classes():
        assert tuple(MODEL_PROFILES[profile.profile]) == profile.steps
        for step in profile.steps:
            request = request_type(profile.profile, step)
            assert STEP_SPECS[step].artifact_type == request.result_type.kind
            assert STEP_SPECS[step].output_argument == request.output_argument


def test_profile_abcs_require_complete_implementations():
    with pytest.raises(TypeError):
        SupervisedAlgorithm()
    with pytest.raises(TypeError, match="inherit"):
        AlgorithmRepository({"probe": ToyAlgorithm})


def test_config_file_resolves_paths_and_rejects_unsupported_values(tmp_path):
    @dataclass(frozen=True)
    class Paths(ModelConfig):
        vocabulary: Path

    config_file = tmp_path / "model.yaml"
    config_file.write_text("vocabulary: assets/vocab.json\n")
    config = Paths.from_file(config_file)
    assert config.vocabulary == (tmp_path / "assets/vocab.json").resolve()
    assert Paths.load(config.save(tmp_path / "resolved.json")) == config

    @dataclass(frozen=True)
    class Number(ModelConfig):
        value: float

    for invalid in (float("nan"), float("inf"), True, "1.0"):
        with pytest.raises(TypeError):
            Number(value=invalid)


def test_predict_only_context_must_be_explicit_and_disjoint(prepared, tmp_path):
    from meds_model_core.requests import PredictionContext, PredictOnlyRequest

    runner, original = prepared
    request = PredictOnlyRequest(
        data=original.data,
        index=original.index,
        context=PredictionContext(original.index.directory, ("train",)),
        output=ArtifactDestination(tmp_path / "context-predictions"),
    )
    assert PredictOnlyRequest.load(request.save(tmp_path / "context-request.json")) == request
    runner.run(AllProfiles(), "predict_only", request, profile="predict_only")
    # A context row with an evaluated key must fail before invoking model code.
    held_out = pl.read_parquet(original.index.directory / "held_out.parquet")
    held_out.write_parquet(original.index.directory / "train.parquet")
    with pytest.raises(ValueError, match="disjoint"):
        runner.run(
            AllProfiles(),
            "predict_only",
            replace(request, output=ArtifactDestination(tmp_path / "bad-context")),
            profile="predict_only",
        )
    assert not (tmp_path / "bad-context").exists()


def test_invalid_model_metadata_or_ground_truth_never_publishes(prepared, tmp_path):
    runner, original = prepared

    class WrongReturn(ToyAlgorithm):
        def predict_supervised(self, request):
            return request.output.directory

    with pytest.raises(TypeError, match="PayloadMetadata"):
        runner.run(WrongReturn(), "predict_supervised", original, profile="supervised")

    class TruthWriter(ToyAlgorithm):
        def predict_supervised(self, request):
            request.index.read().with_columns(
                pl.lit(0.5).alias("predicted_boolean_probability"),
                pl.lit(True).alias("boolean_value"),
            ).write_parquet(request.output.directory / "predictions.parquet")
            return PayloadMetadata("bad")

    with pytest.raises(ValueError, match="ground truth"):
        runner.run(TruthWriter(), "predict_supervised", original, profile="supervised")
    assert not original.output.directory.exists()


def test_sharded_predictions_validate_complete_key_set(prepared):
    runner, original = prepared

    class Sharded(ToyAlgorithm):
        def predict_supervised(self, request):
            frame = request.index.read().with_columns(pl.lit(0.5).alias("predicted_boolean_probability"))
            for i in range(frame.height):
                frame.slice(i, 1).write_parquet(request.output.directory / f"{i}.parquet")
            return PayloadMetadata("shards")

    artifact = runner.run(Sharded(), "predict_supervised", original, profile="supervised")
    assert len(list(artifact.directory.glob("*.parquet"))) == 2


class AllProfiles(
    ToyAlgorithm,
    FinetuneAlgorithm,
    ProbeAlgorithm,
    ZeroShotDirectAlgorithm,
    ZeroShotMaterializedAlgorithm,
    PredictOnlyAlgorithm,
):
    def write_payload(self, request):
        if request.result_type.kind.value == "predictions":
            request.index.read().with_columns(
                pl.lit(0.5).alias("predicted_boolean_probability")
            ).write_parquet(request.output.directory / "predictions.parquet")
            if getattr(request, "task", None) is not None:
                from meds_model_core import RelaxationLedger

                RelaxationLedger("toy", "probability", True).write(request.output.directory)
        else:
            (request.output.directory / "payload").write_text("toy")
        return PayloadMetadata("toy")

    preprocess_data = write_payload
    pretrain = write_payload
    train_supervised = write_payload
    predict_supervised = write_payload
    train_finetune = write_payload
    predict_finetune = write_payload
    infer_embeddings = write_payload
    train_probe = write_payload
    predict_probe = write_payload
    infer_trajectories = write_payload
    predict_zero_shot_direct = write_payload
    predict_zero_shot_materialized = write_payload
    predict_only = write_payload


@pytest.mark.parametrize("profile", [cls.profile for cls in profile_classes()])
def test_every_profile_runs_through_typed_cli_adapter(profile, tmp_path):
    from meds_model_core import STEP_SPECS

    inputs = tmp_path / "inputs"
    inputs.mkdir()
    pl.DataFrame({"subject_id": [1], "prediction_time": [datetime(2020, 1, 1)]}).write_parquet(
        inputs / "held_out.parquet"
    )
    task = tmp_path / "task.yaml"
    task.write_text("description: toy\n")
    repository = AlgorithmRepository({profile: AllProfiles})
    artifacts = {}
    for step in repository.profile_commands():
        spec = STEP_SPECS[step]
        arguments = {spec.output_argument: str(tmp_path / step)}
        for artifact in spec.artifact_inputs:
            arguments[artifact.argument] = str(artifacts[artifact.artifact_type].directory)
        for external in spec.external_arguments:
            arguments[external] = str(task if external == "external_task_criteria_file" else inputs)
        if spec.requires_splits:
            arguments["splits"] = ["held_out"]
        result = repository.run(step, arguments)
        artifacts[result.kind] = result
        assert read_manifest(result.directory)["command"]["name"] == step
