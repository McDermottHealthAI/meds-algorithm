"""One typed request per operation. Field metadata defines the existing CLI path names."""

from __future__ import annotations

from dataclasses import MISSING, dataclass, field, fields
from pathlib import Path
from typing import ClassVar, get_args, get_type_hints

from .artifacts.references import (
    ArtifactDestination,
    ArtifactReference,
    EmbeddingsArtifact,
    FinetunedModelArtifact,
    PredictionsArtifact,
    PreparedDataArtifact,
    PretrainedModelArtifact,
    ProbeModelArtifact,
    SupervisedModelArtifact,
    TrajectoriesArtifact,
)
from .configuration import ExecutionOptions
from .serialization import Serializable
from .tasks.spec import TaskSpec


@dataclass(frozen=True)
class PredictionIndex(Serializable):
    directory: Path
    splits: tuple[str, ...]

    def validate(self):
        if (
            not self.splits
            or len(set(self.splits)) != len(self.splits)
            or any(not s.strip() for s in self.splits)
        ):
            raise ValueError("splits must be a nonempty tuple of unique names")

    def read(self):
        from .data.index import read_index

        return read_index(self.directory, self.splits)


@dataclass(frozen=True)
class TrainingLabels(Serializable):
    directory: Path

    def read(self, split: str = "train"):
        from .data.labels import read_targets

        if split not in ("train", "tuning"):
            raise ValueError("Training labels permit only train and tuning")
        return read_targets(self.directory, (split,))


@dataclass(frozen=True)
class PredictionContext(Serializable):
    directory: Path
    splits: tuple[str, ...]

    def validate(self):
        if (
            not self.splits
            or len(set(self.splits)) != len(self.splits)
            or set(self.splits) - {"train", "tuning"}
        ):
            raise ValueError("Context splits must explicitly select train and/or tuning")

    def read(self, index: PredictionIndex):
        from .data.labels import read_context_labels

        return read_context_labels(
            self.directory, self.splits, index.splits, evaluation_index_dir=index.directory
        )


@dataclass(frozen=True, kw_only=True)
class StepRequest(Serializable):
    output: ArtifactDestination
    execution: ExecutionOptions = field(default_factory=ExecutionOptions)
    predicates_file: Path | None = field(default=None, metadata={"argument": "external_predicates_file"})
    output_argument: ClassVar[str]
    result_type: ClassVar[type[ArtifactReference]]

    @classmethod
    def argument_fields(cls):
        hints = get_type_hints(cls)
        return [(f, hints[f.name]) for f in fields(cls)]

    @classmethod
    def from_arguments(cls, arguments: dict):
        values = dict(arguments)
        output = values.pop(cls.output_argument, None)
        if output is None:
            raise ValueError(f"requires {cls.output_argument}=<path>")
        result = {
            "output": {"directory": output},
            "execution": {"overwrite": values.pop("do_overwrite", False), "seed": values.pop("seed", 0)},
        }
        for f, annotation in cls.argument_fields():
            if f.name in ("output", "execution"):
                continue
            kind = next((t for t in get_args(annotation) if t is not type(None)), annotation)
            key = f.metadata.get("argument")
            if key and key in values:
                value = values.pop(key)
                result[f.name] = (
                    {"directory": value}
                    if isinstance(kind, type) and issubclass(kind, (ArtifactReference, TrainingLabels))
                    else value
                )
            elif kind is PredictionIndex and "external_index_dir" in values:
                result[f.name] = {
                    "directory": values.pop("external_index_dir"),
                    "splits": values.pop("splits", None),
                }
            elif kind is PredictionContext and "external_labels_dir" in values:
                result[f.name] = {
                    "directory": values.pop("external_labels_dir"),
                    "splits": values.pop("context_splits", None),
                }
            elif kind is TaskSpec and "external_task_criteria_file" in values:
                result[f.name] = {
                    "criteria_file": values.pop("external_task_criteria_file"),
                    "predicates_file": arguments.get("external_predicates_file"),
                    "name": values.pop("task_name", None),
                }
        if values:
            raise ValueError(f"Unknown or forbidden arguments for {cls.__name__}: {sorted(values)}")
        for f, _annotation in cls.argument_fields():
            if f.default is MISSING and f.default_factory is MISSING and f.name not in result:
                required = f.metadata.get(
                    "argument",
                    {
                        "index": "external_index_dir and splits",
                        "task": "external_task_criteria_file",
                    }.get(f.name, f.name),
                )
                raise ValueError(f"requires {required}")
        return cls.from_dict(result)

    def artifact_inputs(self):
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, ArtifactReference):
                yield f.metadata["argument"], value


@dataclass(frozen=True, kw_only=True)
class PreprocessDataRequest(StepRequest):
    meds_dir: Path = field(metadata={"argument": "external_meds_dir"})
    output_argument = "output_data_dir"
    result_type = PreparedDataArtifact


@dataclass(frozen=True, kw_only=True)
class PretrainRequest(StepRequest):
    data: PreparedDataArtifact = field(metadata={"argument": "input_data_dir"})
    output_argument = "output_pretrained_model_dir"
    result_type = PretrainedModelArtifact


@dataclass(frozen=True, kw_only=True)
class TrainSupervisedRequest(StepRequest):
    data: PreparedDataArtifact = field(metadata={"argument": "input_data_dir"})
    labels: TrainingLabels = field(metadata={"argument": "external_labels_dir"})
    output_argument = "output_supervised_model_dir"
    result_type = SupervisedModelArtifact


@dataclass(frozen=True, kw_only=True)
class TrainFinetuneRequest(StepRequest):
    data: PreparedDataArtifact = field(metadata={"argument": "input_data_dir"})
    pretrained: PretrainedModelArtifact = field(metadata={"argument": "input_pretrained_model_dir"})
    labels: TrainingLabels = field(metadata={"argument": "external_labels_dir"})
    output_argument = "output_finetuned_model_dir"
    result_type = FinetunedModelArtifact


@dataclass(frozen=True, kw_only=True)
class InferEmbeddingsRequest(StepRequest):
    data: PreparedDataArtifact = field(metadata={"argument": "input_data_dir"})
    pretrained: PretrainedModelArtifact = field(metadata={"argument": "input_pretrained_model_dir"})
    index: PredictionIndex
    output_argument = "output_embeddings_dir"
    result_type = EmbeddingsArtifact


@dataclass(frozen=True, kw_only=True)
class TrainProbeRequest(StepRequest):
    embeddings: EmbeddingsArtifact = field(metadata={"argument": "input_embeddings_dir"})
    labels: TrainingLabels = field(metadata={"argument": "external_labels_dir"})
    output_argument = "output_probe_model_dir"
    result_type = ProbeModelArtifact


@dataclass(frozen=True, kw_only=True)
class PredictSupervisedRequest(StepRequest):
    data: PreparedDataArtifact = field(metadata={"argument": "input_data_dir"})
    model: SupervisedModelArtifact = field(metadata={"argument": "input_supervised_model_dir"})
    index: PredictionIndex
    output_argument = "output_predictions_dir"
    result_type = PredictionsArtifact


@dataclass(frozen=True, kw_only=True)
class PredictFinetuneRequest(StepRequest):
    data: PreparedDataArtifact = field(metadata={"argument": "input_data_dir"})
    model: FinetunedModelArtifact = field(metadata={"argument": "input_finetuned_model_dir"})
    index: PredictionIndex
    output_argument = "output_predictions_dir"
    result_type = PredictionsArtifact


@dataclass(frozen=True, kw_only=True)
class PredictProbeRequest(StepRequest):
    embeddings: EmbeddingsArtifact = field(metadata={"argument": "input_embeddings_dir"})
    model: ProbeModelArtifact = field(metadata={"argument": "input_probe_model_dir"})
    index: PredictionIndex
    output_argument = "output_predictions_dir"
    result_type = PredictionsArtifact


@dataclass(frozen=True, kw_only=True)
class PredictZeroShotDirectRequest(StepRequest):
    data: PreparedDataArtifact = field(metadata={"argument": "input_data_dir"})
    pretrained: PretrainedModelArtifact = field(metadata={"argument": "input_pretrained_model_dir"})
    index: PredictionIndex
    task: TaskSpec
    output_argument = "output_predictions_dir"
    result_type = PredictionsArtifact


@dataclass(frozen=True, kw_only=True)
class InferTrajectoriesRequest(StepRequest):
    data: PreparedDataArtifact = field(metadata={"argument": "input_data_dir"})
    pretrained: PretrainedModelArtifact = field(metadata={"argument": "input_pretrained_model_dir"})
    index: PredictionIndex
    output_argument = "output_trajectories_dir"
    result_type = TrajectoriesArtifact


@dataclass(frozen=True, kw_only=True)
class PredictZeroShotMaterializedRequest(StepRequest):
    data: PreparedDataArtifact = field(metadata={"argument": "input_data_dir"})
    trajectories: TrajectoriesArtifact = field(metadata={"argument": "input_trajectories_dir"})
    meds_dir: Path = field(metadata={"argument": "external_meds_dir"})
    index: PredictionIndex
    task: TaskSpec
    output_argument = "output_predictions_dir"
    result_type = PredictionsArtifact


@dataclass(frozen=True, kw_only=True)
class PredictOnlyRequest(StepRequest):
    data: PreparedDataArtifact = field(metadata={"argument": "input_data_dir"})
    index: PredictionIndex
    context: PredictionContext | None = None
    task: TaskSpec | None = None
    output_argument = "output_predictions_dir"
    result_type = PredictionsArtifact
