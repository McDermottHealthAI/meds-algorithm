"""The common NN interface remains typed, extensible and usable without a training framework."""

from dataclasses import FrozenInstanceError, dataclass, replace

import pytest

from meds_algorithm_core import (
    AlgorithmConfig,
    AlgorithmRepository,
    NNConfig,
    PayloadMetadata,
    SupervisedAlgorithm,
    read_manifest,
)


@dataclass(frozen=True)
class AttentionConfig(NNConfig):
    learning_rate: float = 0.001
    batch_size: int = 16
    reference_width: int = 32
    heads: int = 4

    @property
    def hidden_size(self) -> int:
        # Example policy: scale width, round down to full heads, and retain at least one per head.
        return max(1, int(self.reference_width * self.capacity / self.heads)) * self.heads

    def validate(self):
        super().validate()
        if self.heads < 1 or self.reference_width < 1 or self.reference_width % self.heads:
            raise ValueError("reference_width must be positive and divisible by positive heads")


class RecordingNN(SupervisedAlgorithm):
    name = "recording_nn"
    config_type = AttentionConfig

    def preprocess_data(self, request):
        (request.output.directory / "settings.txt").write_text(str(self.config.hidden_size))
        return PayloadMetadata("configuration-test")

    def train_supervised(self, request):
        raise NotImplementedError

    def predict_supervised(self, request):
        raise NotImplementedError


def test_nn_config_subclass_roundtrip_and_capacity_sweep(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text(
        "capacity: 0.5\nreference_width: 64\nheads: 8\nlearning_rate: 0.002\n"
        "batch_size: 8\nweight_decay: 0.01\ndropout: 0.1\n"
        "additional_predicates_file: extra.yaml\n"
    )
    config = AttentionConfig.from_file(path)
    assert isinstance(config, AlgorithmConfig)
    assert config.hidden_size == 32
    assert config.additional_predicates_file == tmp_path / "extra.yaml"
    assert AttentionConfig.load(config.save(tmp_path / "config.json")) == config
    sweep = [replace(config, capacity=scale) for scale in (0.5, 1.0, 2.0)]
    assert [item.hidden_size for item in sweep] == [32, 64, 128]
    assert all(item.learning_rate == config.learning_rate for item in sweep)
    assert config.capacity == 0.5
    with pytest.raises(FrozenInstanceError):
        config.capacity = 2.0
    with pytest.raises(ValueError, match="type or schema"):
        NNConfig.load(tmp_path / "config.json")
    # Loading a concrete configuration with a base class cannot silently discard local fields.
    with pytest.raises(ValueError, match="Unknown fields"):
        NNConfig.from_dict(config.to_dict())


@pytest.mark.parametrize(
    "values",
    [
        {"capacity": 0},
        {"capacity": -1},
        {"capacity": float("inf")},
        {"capacity": float("nan")},
        {"capacity": True},
        {"capacity": "0.5"},
        {"capacity": {"width": 32, "depth": 2}},
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
        {"heads": 0},
        {"reference_width": 0},
        {"reference_width": 33},
        {"lr": 0.01},
        {"bs": 16},
    ],
)
def test_nn_config_rejects_invalid_values_from_python_and_files(values):
    with pytest.raises((ValueError, TypeError)):
        AttentionConfig(**values)
    with pytest.raises((ValueError, TypeError)):
        AttentionConfig.from_dict(values)


def test_nn_config_requires_explicit_training_settings():
    with pytest.raises(TypeError):
        NNConfig()
    config = NNConfig(learning_rate=1, batch_size=1)
    assert config.learning_rate == config.capacity == 1.0
    assert config.dropout == config.weight_decay == 0.0
    assert AlgorithmConfig().to_dict() == {"additional_predicates_file": None}


def test_repository_records_nn_settings_from_config_file(tmp_path):
    meds = tmp_path / "meds"
    meds.mkdir()
    config_file = tmp_path / "settings.yaml"
    config_file.write_text("capacity: 2.0\nreference_width: 64\nheads: 8\nbatch_size: 32\n")
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
    assert config.capacity == 2.0 and config.hidden_size == 128
    assert config.batch_size == 32
    assert read_manifest(output)["algorithm"]["config"] == config.to_dict()
    assert (output / "settings.txt").read_text() == "128"
