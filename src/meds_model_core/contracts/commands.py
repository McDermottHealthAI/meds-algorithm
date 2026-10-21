"""Profile selection, distinct command contracts, and backend-neutral dispatch."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class CommandName(StrEnum):
    preprocess_data = "preprocess_data"
    pretrain = "pretrain"
    train_supervised = "train_supervised"
    predict_supervised = "predict_supervised"
    train_finetune = "train_finetune"
    predict_finetune = "predict_finetune"
    infer_embeddings = "infer_embeddings"
    train_probe = "train_probe"
    predict_probe = "predict_probe"
    predict_zero_shot_direct = "predict_zero_shot_direct"
    infer_trajectories = "infer_trajectories"
    predict_zero_shot_materialized = "predict_zero_shot_materialized"
    predict_only = "predict_only"


class ArtifactType(StrEnum):
    patients = "patients"
    pretrained_model = "pretrained_model"
    embeddings = "embeddings"
    trajectories = "trajectories"
    supervised_model = "supervised_model"
    finetuned_model = "finetuned_model"
    probe_model = "probe_model"
    predictions = "predictions"


MODEL_PROFILES: dict[str, tuple[CommandName, ...]] = {
    "supervised": (CommandName.preprocess_data, CommandName.train_supervised, CommandName.predict_supervised),
    "finetune": (
        CommandName.preprocess_data,
        CommandName.pretrain,
        CommandName.train_finetune,
        CommandName.predict_finetune,
    ),
    "probe": (
        CommandName.preprocess_data,
        CommandName.pretrain,
        CommandName.infer_embeddings,
        CommandName.train_probe,
        CommandName.predict_probe,
    ),
    "zero_shot_direct": (
        CommandName.preprocess_data,
        CommandName.pretrain,
        CommandName.predict_zero_shot_direct,
    ),
    "zero_shot_materialized": (
        CommandName.preprocess_data,
        CommandName.pretrain,
        CommandName.infer_trajectories,
        CommandName.predict_zero_shot_materialized,
    ),
    "predict_only": (CommandName.preprocess_data, CommandName.predict_only),
}

ZERO_SHOT_TASK_COMMANDS = {
    name: frozenset({commands[-1]})
    for name, commands in MODEL_PROFILES.items()
    if name.startswith("zero_shot_")
}


@dataclass(frozen=True)
class ArtifactInput:
    """Required upstream envelope; payload format/identity checks remain model-owned."""

    argument: str
    artifact_type: ArtifactType


@dataclass(frozen=True)
class StepSpec:
    """Executable boundary specification, independent of the computational backend."""

    artifact_type: ArtifactType
    output_argument: str
    artifact_inputs: tuple[ArtifactInput, ...] = ()
    external_arguments: tuple[str, ...] = ()
    requires_splits: bool = False
    label_access: str = "none"
    task_conditioned: bool = False

    def validate(self, arguments: Mapping[str, Any]) -> None:
        paths = (
            self.output_argument,
            *self.external_arguments,
            *(item.argument for item in self.artifact_inputs),
        )
        for key in paths:
            value = arguments.get(key)
            if not isinstance(value, (str, Path)) or not str(value).strip():
                raise ValueError(f"requires {key}=<path>")
        if "do_overwrite" in arguments and not isinstance(arguments["do_overwrite"], bool):
            raise ValueError("do_overwrite must be a boolean")
        if self.label_access == "none" and "external_labels_dir" in arguments:
            raise ValueError("use external_index_dir for keys; this step cannot consume training labels")
        splits = arguments.get("splits")
        if (self.requires_splits or splits is not None) and (
            not isinstance(splits, (list, tuple))
            or not splits
            or any(not isinstance(s, str) or not s.strip() for s in splits)
            or len(set(splits)) != len(splits)
        ):
            raise ValueError("splits must be an explicit nonempty list of unique split names")
        if (
            not self.task_conditioned
            and "external_task_criteria_file" in arguments
            and self.label_access != "context_only"
        ):
            raise ValueError("this command is task-independent; do not pass external_task_criteria_file")


DATA = ArtifactInput("input_data_dir", ArtifactType.patients)
PRETRAINED = ArtifactInput("input_pretrained_model_dir", ArtifactType.pretrained_model)
INDEX = ("external_index_dir",)
LABELS = ("external_labels_dir",)
STEP_SPECS: dict[CommandName, StepSpec] = {
    CommandName.preprocess_data: StepSpec(
        ArtifactType.patients, "output_data_dir", external_arguments=("external_meds_dir",)
    ),
    CommandName.pretrain: StepSpec(ArtifactType.pretrained_model, "output_pretrained_model_dir", (DATA,)),
    CommandName.train_supervised: StepSpec(
        ArtifactType.supervised_model,
        "output_supervised_model_dir",
        (DATA,),
        LABELS,
        label_access="train_tuning",
    ),
    CommandName.train_finetune: StepSpec(
        ArtifactType.finetuned_model,
        "output_finetuned_model_dir",
        (DATA, PRETRAINED),
        LABELS,
        label_access="train_tuning",
    ),
    CommandName.infer_embeddings: StepSpec(
        ArtifactType.embeddings, "output_embeddings_dir", (DATA, PRETRAINED), INDEX, requires_splits=True
    ),
    CommandName.train_probe: StepSpec(
        ArtifactType.probe_model,
        "output_probe_model_dir",
        (ArtifactInput("input_embeddings_dir", ArtifactType.embeddings),),
        LABELS,
        label_access="train_tuning",
    ),
    CommandName.predict_supervised: StepSpec(
        ArtifactType.predictions,
        "output_predictions_dir",
        (DATA, ArtifactInput("input_supervised_model_dir", ArtifactType.supervised_model)),
        INDEX,
        True,
    ),
    CommandName.predict_finetune: StepSpec(
        ArtifactType.predictions,
        "output_predictions_dir",
        (DATA, ArtifactInput("input_finetuned_model_dir", ArtifactType.finetuned_model)),
        INDEX,
        True,
    ),
    CommandName.predict_probe: StepSpec(
        ArtifactType.predictions,
        "output_predictions_dir",
        (
            ArtifactInput("input_embeddings_dir", ArtifactType.embeddings),
            ArtifactInput("input_probe_model_dir", ArtifactType.probe_model),
        ),
        INDEX,
        True,
    ),
    CommandName.predict_zero_shot_direct: StepSpec(
        ArtifactType.predictions,
        "output_predictions_dir",
        (DATA, PRETRAINED),
        (*INDEX, "external_task_criteria_file"),
        True,
        task_conditioned=True,
    ),
    CommandName.infer_trajectories: StepSpec(
        ArtifactType.trajectories, "output_trajectories_dir", (DATA, PRETRAINED), INDEX, True
    ),
    CommandName.predict_zero_shot_materialized: StepSpec(
        ArtifactType.predictions,
        "output_predictions_dir",
        (DATA, ArtifactInput("input_trajectories_dir", ArtifactType.trajectories)),
        (*INDEX, "external_meds_dir", "external_task_criteria_file"),
        True,
        task_conditioned=True,
    ),
    CommandName.predict_only: StepSpec(
        ArtifactType.predictions, "output_predictions_dir", (DATA,), INDEX, True, label_access="context_only"
    ),
}


class Command(ABC):
    """Implement run; dispatch validates argument shapes before invoking model code."""

    name: CommandName

    @abstractmethod
    def run(self, arguments: Mapping[str, Any]) -> Path:
        """Validate upstream compatibility, run, and return a published artifact directory."""

    def __call__(self, arguments: Mapping[str, Any]) -> Path:
        STEP_SPECS[self.name].validate(arguments)
        return self.run(arguments)


class ModelRepository:
    """One registry for the union of declared profiles; explicit selection when ambiguous."""

    def __init__(self, profiles: Sequence[str], commands: Mapping[CommandName, type[Command]]) -> None:
        if isinstance(profiles, str) or not profiles or len(set(profiles)) != len(profiles):
            raise ValueError("profiles must be a nonempty sequence of unique profile names")
        unknown = set(profiles) - MODEL_PROFILES.keys()
        if unknown:
            raise ValueError(f"Unknown model profiles: {sorted(unknown)}")
        expected = {command for profile in profiles for command in MODEL_PROFILES[profile]}
        if set(commands) != expected:
            raise ValueError(f"Declared profiles require {sorted(expected)}; got {sorted(commands)}")
        for name, implementation in commands.items():
            if not isinstance(implementation, type) or not issubclass(implementation, Command):
                raise TypeError(f"{name} must register a Command subclass")
            if implementation.name != name:
                raise ValueError(f"{name} registers a class named {implementation.name}")
        self.profiles = tuple(profiles)
        self.commands = dict(commands)

    def select_profile(self, profile: str | None = None) -> str:
        if profile is None:
            if len(self.profiles) != 1:
                raise ValueError("Several profiles are declared; select one with --profile")
            return self.profiles[0]
        if profile not in self.profiles:
            raise ValueError(f"Profile {profile!r} is not declared: {self.profiles}")
        return profile

    def profile_commands(self, profile: str | None = None) -> tuple[CommandName, ...]:
        return MODEL_PROFILES[self.select_profile(profile)]

    def run(
        self, name: CommandName | str, arguments: Mapping[str, Any], *, profile: str | None = None
    ) -> Path:
        selected = self.select_profile(profile)
        command_name = CommandName(name)
        if command_name not in MODEL_PROFILES[selected]:
            raise ValueError(f"{command_name.value} is not part of the {selected} model profile")
        return self.commands[command_name]()(arguments)
