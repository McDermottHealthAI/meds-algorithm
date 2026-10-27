"""Shared MEDS model infrastructure; data dependencies are imported only when used."""

from .algorithms import (
    Algorithm,
    FinetuneAlgorithm,
    PredictOnlyAlgorithm,
    PretrainedAlgorithm,
    ProbeAlgorithm,
    SupervisedAlgorithm,
    ZeroShotDirectAlgorithm,
    ZeroShotMaterializedAlgorithm,
)
from .artifacts.manifest import digest_config, digest_file, measured_artifact, read_manifest
from .artifacts.references import (
    ArtifactDestination,
    ArtifactReference,
    EmbeddingsArtifact,
    FinetunedModelArtifact,
    PayloadMetadata,
    PredictionsArtifact,
    PreparedDataArtifact,
    PretrainedModelArtifact,
    ProbeModelArtifact,
    SupervisedModelArtifact,
    TrajectoriesArtifact,
)
from .artifacts.results import write_run_result
from .configuration import ExecutionOptions, ModelConfig
from .contracts.commands import (
    MODEL_PROFILES,
    STEP_SPECS,
    ZERO_SHOT_TASK_COMMANDS,
    ArtifactInput,
    ArtifactType,
    Command,
    CommandName,
    ModelRepository,
    StepSpec,
)
from .data.index import read_index, split_files
from .data.labels import read_context_labels
from .evaluation.predictions import attach_ground_truth, check_decoded
from .runner import AlgorithmRepository, StepRunner
from .tasks.spec import RelaxationLedger, TaskSpec
from .version import CONTRACT_VERSION

__all__ = [
    "CONTRACT_VERSION",
    "MODEL_PROFILES",
    "STEP_SPECS",
    "ZERO_SHOT_TASK_COMMANDS",
    "Algorithm",
    "AlgorithmRepository",
    "ArtifactDestination",
    "ArtifactInput",
    "ArtifactReference",
    "ArtifactType",
    "Command",
    "CommandName",
    "EmbeddingsArtifact",
    "ExecutionOptions",
    "FinetuneAlgorithm",
    "FinetunedModelArtifact",
    "ModelConfig",
    "ModelRepository",
    "PayloadMetadata",
    "PredictOnlyAlgorithm",
    "PredictionsArtifact",
    "PreparedDataArtifact",
    "PretrainedAlgorithm",
    "PretrainedModelArtifact",
    "ProbeAlgorithm",
    "ProbeModelArtifact",
    "RelaxationLedger",
    "StepRunner",
    "StepSpec",
    "SupervisedAlgorithm",
    "SupervisedModelArtifact",
    "TaskSpec",
    "TrajectoriesArtifact",
    "ZeroShotDirectAlgorithm",
    "ZeroShotMaterializedAlgorithm",
    "attach_ground_truth",
    "check_decoded",
    "digest_config",
    "digest_file",
    "measured_artifact",
    "read_context_labels",
    "read_index",
    "read_manifest",
    "split_files",
    "write_run_result",
]
