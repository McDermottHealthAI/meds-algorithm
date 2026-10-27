"""Algorithm-owned configuration types and shared per-invocation execution options."""

from dataclasses import dataclass
from pathlib import Path

import yaml

from .serialization import Serializable


@dataclass(frozen=True)
class AlgorithmConfig(Serializable):
    """Extend in a algorithm repository with typed fields, defaults and validate()."""

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


@dataclass(frozen=True)
class ExecutionOptions(Serializable):
    seed: int = 0
    overwrite: bool = False

    def validate(self):
        if self.seed < 0:
            raise ValueError("seed must be nonnegative")
