"""Algorithm-owned configuration types and shared per-invocation execution options."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .serialization import Serializable


@dataclass(frozen=True)
class AlgorithmConfig(Serializable):
    """Parent for algorithm-owned typed configuration, defaults and validation."""

    additional_predicates_file: Path | None = field(default=None, kw_only=True)

    @classmethod
    def from_file(cls, path: Path | str):
        """Read a user JSON/YAML values file, or an exact serialized config.json envelope."""
        path = Path(path).resolve()
        values = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(values, dict):
            raise TypeError("Configuration file must contain an object")
        if set(values) == {"schema_version", "type", "values"}:
            return cls.load(path)
        return cls.from_dict(values, base=path.parent)


@dataclass(frozen=True, kw_only=True)
class NNCapacity(Serializable):
    """Architecture dimensions, not a parameter count; algorithms define their exact meaning."""

    width: int
    depth: int

    def validate(self):
        if self.width < 1 or self.depth < 1:
            raise ValueError("capacity width and depth must be positive")


@dataclass(frozen=True, kw_only=True)
class NNConfig(AlgorithmConfig):
    """Framework-independent neural-network settings; concrete algorithms supply training defaults.

    batch_size is examples per device per microbatch, before gradient accumulation.
    Subclasses overriding validate() must call super().validate().
    """

    capacity: NNCapacity
    learning_rate: float
    batch_size: int
    weight_decay: float = 0.0
    dropout: float = 0.0

    def validate(self):
        super().validate()
        if self.learning_rate <= 0:
            raise ValueError("learning_rate must be positive")
        if self.batch_size < 1:
            raise ValueError("batch_size must be positive")
        if self.weight_decay < 0:
            raise ValueError("weight_decay must be nonnegative")
        if not 0 <= self.dropout < 1:
            raise ValueError("dropout must be in [0, 1)")


@dataclass(frozen=True)
class ExecutionOptions(Serializable):
    seed: int = 0
    overwrite: bool = False

    def validate(self):
        if self.seed < 0:
            raise ValueError("seed must be nonnegative")
