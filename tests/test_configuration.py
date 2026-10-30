"""The common NN interface remains typed, extensible and usable without a training framework."""

from dataclasses import FrozenInstanceError, dataclass, field, replace

import pytest

from meds_algorithm_core import (
    AlgorithmConfig,
    AlgorithmRepository,
    NNCapacity,
    NNConfig,
    PayloadMetadata,
    SupervisedAlgorithm,
    read_manifest,
)


@dataclass(frozen=True, kw_only=True)
class AttentionCapacity(NNCapacity):
    heads: int = 4

    def validate(self):
        super().validate()
        if self.heads < 1 or self.width % self.heads:
            raise ValueError("width must be divisible by positive heads")


@dataclass(frozen=True)
class AttentionConfig(NNConfig):
    capacity: AttentionCapacity = field(default_factory=lambda: AttentionCapacity(width=32, depth=2))
    learning_rate: float = 0.001
    batch_size: int = 16


class RecordingNN(SupervisedAlgorithm):
    name = "recording_nn"
    config_type = AttentionConfig

    def preprocess_data(self, request):
        (request.output.directory / "settings.txt").write_text(str(self.config.capacity.heads))
        return PayloadMetadata("configuration-test")

    def train_supervised(self, request):
        raise NotImplementedError

    def predict_supervised(self, request):
        raise NotImplementedError


def test_nn_config_nested_subclass_roundtrip_and_sweep(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text(
        "capacity: {width: 64, depth: 3, heads: 8}\nlearning_rate: 0.002\n"
        "batch_size: 8\nweight_decay: 0.01\ndropout: 0.1\n"
        "additional_predicates_file: extra.yaml\n"
    )
    config = AttentionConfig.from_file(path)
    assert isinstance(config, AlgorithmConfig)
    assert type(config.capacity) is AttentionCapacity
    assert config.additional_predicates_file == tmp_path / "extra.yaml"
    assert AttentionConfig.load(config.save(tmp_path / "config.json")) == config
    larger = replace(config, capacity=replace(config.capacity, width=128))
    assert larger.capacity.width == 128 and config.capacity.width == 64
    assert larger.learning_rate == config.learning_rate
    with pytest.raises(FrozenInstanceError):
        config.capacity.width = 128
    with pytest.raises(ValueError, match="type or schema"):
        NNConfig.load(tmp_path / "config.json")
    # A concrete capacity annotation is required: base capacity cannot silently discard extra axes.
    with pytest.raises(ValueError, match="Unknown fields"):
        NNConfig.from_dict(config.to_dict())


@pytest.mark.parametrize(
    "values",
    [
        {"learning_rate": 0},
        {"learning_rate": float("inf")},
        {"learning_rate": True},
        {"batch_size": 0},
        {"batch_size": 1.5},
        {"batch_size": True},
        {"weight_decay": -0.1},
        {"dropout": -0.1},
        {"dropout": 1.0},
        {"dropout": float("nan")},
        {"capacity": {"width": 0, "depth": 2}},
        {"capacity": {"width": 32, "depth": -1}},
        {"capacity": {"width": True, "depth": 2}},
        {"capacity": {"width": 32, "depth": 2, "heads": 3}},
        {"capacity": {"width": 32, "depth": 2, "unknown": 1}},
        {"lr": 0.01},
        {"bs": 16},
    ],
)
def test_nn_config_rejects_invalid_values_from_python_and_files(values):
    with pytest.raises((ValueError, TypeError)):
        AttentionConfig(**values)
    with pytest.raises((ValueError, TypeError)):
        AttentionConfig.from_dict(values)


def test_nn_config_requires_explicit_architecture_and_training_settings():
    with pytest.raises(TypeError):
        NNConfig()
    config = NNConfig(capacity=NNCapacity(width=16, depth=1), learning_rate=1, batch_size=1)
    assert config.learning_rate == 1.0
    assert config.dropout == config.weight_decay == 0.0
    assert AlgorithmConfig().to_dict() == {"additional_predicates_file": None}


def test_repository_records_nn_settings_from_config_file(tmp_path):
    meds = tmp_path / "meds"
    meds.mkdir()
    config_file = tmp_path / "settings.yaml"
    config_file.write_text("capacity: {width: 64, depth: 4, heads: 8}\nbatch_size: 32\n")
    output = tmp_path / "prepared"
    AlgorithmRepository({"supervised": RecordingNN}).run(
        "preprocess_data",
        {
            "config_file": str(config_file),
            "external_meds_dir": str(meds),
            "output_data_dir": str(output),
        },
        profile="supervised",
    )
    config = AttentionConfig.load(output / "config.json")
    assert config.capacity == AttentionCapacity(width=64, depth=4, heads=8)
    assert config.batch_size == 32
    assert read_manifest(output)["algorithm"]["config"] == config.to_dict()
    assert (output / "settings.txt").read_text() == "8"
