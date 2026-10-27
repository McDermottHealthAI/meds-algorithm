"""Immutable, lazy references to persisted artifacts; no payload loading at construction."""

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from ..contracts.enums import ArtifactType
from ..serialization import Serializable


@dataclass(frozen=True)
class ArtifactReference(Serializable):
    directory: Path
    kind: ClassVar[ArtifactType]

    @classmethod
    def open(cls, directory: Path | str):
        reference = cls(Path(directory))
        reference.read_manifest()
        return reference

    def read_manifest(self) -> dict:
        from .manifest import read_manifest

        manifest = read_manifest(self.directory)
        if manifest["artifact"]["type"] != self.kind.value:
            raise ValueError(f"Expected {self.kind.value} artifact: {self.directory}")
        return manifest


class PreparedDataArtifact(ArtifactReference):
    kind = ArtifactType.patients


class PretrainedAlgorithmArtifact(ArtifactReference):
    kind = ArtifactType.pretrained_algorithm


class EmbeddingsArtifact(ArtifactReference):
    kind = ArtifactType.embeddings


class TrajectoriesArtifact(ArtifactReference):
    kind = ArtifactType.trajectories


class SupervisedAlgorithmArtifact(ArtifactReference):
    kind = ArtifactType.supervised_algorithm


class FinetunedAlgorithmArtifact(ArtifactReference):
    kind = ArtifactType.finetuned_algorithm


class ProbeAlgorithmArtifact(ArtifactReference):
    kind = ArtifactType.probe_algorithm


class PredictionsArtifact(ArtifactReference):
    kind = ArtifactType.predictions


@dataclass(frozen=True)
class ArtifactDestination(Serializable):
    """Final destination for callers; runner substitutes its private staging path for algorithm code."""

    directory: Path


@dataclass(frozen=True)
class PayloadMetadata(Serializable):
    """Algorithm methods describe their payload; only the runner publishes the final artifact."""

    format: str
    version: int = 1

    def validate(self):
        if not self.format.strip() or self.version < 1:
            raise ValueError("Payload format must be nonempty and version must be positive")
