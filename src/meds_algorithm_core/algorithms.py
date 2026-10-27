"""Profile ABCs are the authority for lifecycle order and typed operation signatures."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, get_type_hints

from .artifacts.references import PayloadMetadata
from .configuration import AlgorithmConfig
from .contracts.enums import CommandName
from .requests import (
    InferEmbeddingsRequest,
    InferTrajectoriesRequest,
    PredictFinetuneRequest,
    PredictOnlyRequest,
    PredictProbeRequest,
    PredictSupervisedRequest,
    PredictZeroShotDirectRequest,
    PredictZeroShotMaterializedRequest,
    PreprocessDataRequest,
    PretrainRequest,
    StepRequest,
    TrainFinetuneRequest,
    TrainProbeRequest,
    TrainSupervisedRequest,
)


class Algorithm(ABC):
    name: ClassVar[str]
    config_type: ClassVar[type[AlgorithmConfig]] = AlgorithmConfig

    def __init__(self, config: AlgorithmConfig | None = None):
        self.config = self.config_type() if config is None else config
        if type(self.config) is not self.config_type:
            raise TypeError(f"Expected {self.config_type.__name__}")
        if not getattr(self, "name", "").strip():
            raise ValueError("Algorithm.name must be nonempty")
        self.config.validate()

    @abstractmethod
    def preprocess_data(self, request: PreprocessDataRequest) -> PayloadMetadata:
        """Write task-independent prepared data into request.output.directory."""

    def validate_inputs(self, request: StepRequest) -> None:
        """Default: fitted inputs must match this algorithm and resolved configuration.

        Extend for payload/vocabulary/cutoff checks. Override deliberately if a documented family
        supports compatible external pretrained algorithms or different training/inference settings.
        """
        for _, artifact in request.artifact_inputs():
            if artifact.kind.value.endswith("algorithm"):
                producer = artifact.read_manifest().get("algorithm", {})
                if producer.get("name") != self.name or producer.get("config") != self.config.to_dict():
                    raise ValueError(
                        "Algorithm algorithm/configuration mismatch; load its recorded configuration"
                    )


class SupervisedAlgorithm(Algorithm):
    profile = "supervised"
    steps = ("preprocess_data", "train_supervised", "predict_supervised")

    @abstractmethod
    def train_supervised(self, request: TrainSupervisedRequest) -> PayloadMetadata: ...

    @abstractmethod
    def predict_supervised(self, request: PredictSupervisedRequest) -> PayloadMetadata: ...


class PretrainedAlgorithm(Algorithm):
    @abstractmethod
    def pretrain(self, request: PretrainRequest) -> PayloadMetadata: ...


class FinetuneAlgorithm(PretrainedAlgorithm):
    profile = "finetune"
    steps = ("preprocess_data", "pretrain", "train_finetune", "predict_finetune")

    @abstractmethod
    def train_finetune(self, request: TrainFinetuneRequest) -> PayloadMetadata: ...

    @abstractmethod
    def predict_finetune(self, request: PredictFinetuneRequest) -> PayloadMetadata: ...


class ProbeAlgorithm(PretrainedAlgorithm):
    profile = "probe"
    steps = ("preprocess_data", "pretrain", "infer_embeddings", "train_probe", "predict_probe")

    @abstractmethod
    def infer_embeddings(self, request: InferEmbeddingsRequest) -> PayloadMetadata: ...

    @abstractmethod
    def train_probe(self, request: TrainProbeRequest) -> PayloadMetadata: ...

    @abstractmethod
    def predict_probe(self, request: PredictProbeRequest) -> PayloadMetadata: ...


class ZeroShotDirectAlgorithm(PretrainedAlgorithm):
    profile = "zero_shot_direct"
    steps = ("preprocess_data", "pretrain", "predict_zero_shot_direct")

    @abstractmethod
    def predict_zero_shot_direct(self, request: PredictZeroShotDirectRequest) -> PayloadMetadata: ...


class ZeroShotMaterializedAlgorithm(PretrainedAlgorithm):
    profile = "zero_shot_materialized"
    steps = ("preprocess_data", "pretrain", "infer_trajectories", "predict_zero_shot_materialized")

    @abstractmethod
    def infer_trajectories(self, request: InferTrajectoriesRequest) -> PayloadMetadata: ...

    @abstractmethod
    def predict_zero_shot_materialized(
        self, request: PredictZeroShotMaterializedRequest
    ) -> PayloadMetadata: ...


class PredictOnlyAlgorithm(Algorithm):
    profile = "predict_only"
    steps = ("preprocess_data", "predict_only")

    @abstractmethod
    def predict_only(self, request: PredictOnlyRequest) -> PayloadMetadata: ...


def profile_classes() -> tuple[type[Algorithm], ...]:
    """Explicit built-ins; no plugin discovery or duplicated command specification."""
    return (
        SupervisedAlgorithm,
        FinetuneAlgorithm,
        ProbeAlgorithm,
        ZeroShotDirectAlgorithm,
        ZeroShotMaterializedAlgorithm,
        PredictOnlyAlgorithm,
    )


def profile_class(profile: str) -> type[Algorithm]:
    for cls in profile_classes():
        if cls.profile == profile:
            return cls
    raise ValueError(f"Unknown algorithm profile: {profile}")


def request_type(profile: str, step: str | CommandName) -> type[StepRequest]:
    cls = profile_class(profile)
    if step not in cls.steps:
        raise ValueError(f"{step} is not part of the {profile} algorithm profile")
    return get_type_hints(getattr(cls, step))["request"]
