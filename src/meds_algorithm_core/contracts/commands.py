"""Derived legacy contract views and compatibility dispatch.

Profile ABCs own lifecycle order; typed requests own argument definitions. These views keep existing
manifest readers and callers working without maintaining a second specification.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import MISSING, dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from ..algorithms import profile_classes, request_type
from ..artifacts.references import ArtifactReference
from ..requests import PredictionIndex, TrainingLabels
from ..tasks.spec import TaskSpec
from .enums import ArtifactType as ArtifactType
from .enums import CommandName as CommandName


@dataclass(frozen=True)
class ArtifactInput:
    """Required upstream envelope; payload format/identity checks remain algorithm-owned."""

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


def _step_spec(request):
    artifacts = []
    external = []
    requires_splits = False
    label_access = "none"
    task_conditioned = False
    for field, kind in request.argument_fields():
        if field.name in ("output", "execution"):
            continue
        required = field.default is MISSING and field.default_factory is MISSING
        if isinstance(kind, type) and issubclass(kind, ArtifactReference):
            artifacts.append(ArtifactInput(field.metadata["argument"], kind.kind))
        elif kind is PredictionIndex:
            external.append("external_index_dir")
            requires_splits = True
        elif kind is TrainingLabels:
            external.append("external_labels_dir")
            label_access = "train_tuning"
        elif kind is TaskSpec:
            external.append("external_task_criteria_file")
            task_conditioned = True
        elif field.name == "context":
            label_access = "context_only"
        elif required and "argument" in field.metadata:
            external.append(field.metadata["argument"])
    return StepSpec(
        request.result_type.kind,
        request.output_argument,
        tuple(artifacts),
        tuple(external),
        requires_splits,
        label_access,
        task_conditioned,
    )


ALGORITHM_PROFILES = MappingProxyType(
    {cls.profile: tuple(CommandName(step) for step in cls.steps) for cls in profile_classes()}
)
STEP_SPECS = MappingProxyType(
    {
        step: _step_spec(request_type(profile, step))
        for profile, steps in ALGORITHM_PROFILES.items()
        for step in steps
    }
)
ZERO_SHOT_TASK_COMMANDS = MappingProxyType(
    {
        profile: frozenset(step for step in steps if STEP_SPECS[step].task_conditioned)
        for profile, steps in ALGORITHM_PROFILES.items()
        if profile.startswith("zero_shot_")
    }
)


class Command(ABC):
    """Implement run; dispatch validates argument shapes before invoking algorithm code."""

    name: CommandName

    @abstractmethod
    def run(self, arguments: Mapping[str, Any]) -> Path:
        """Validate upstream compatibility, run, and return a published artifact directory."""

    def __call__(self, arguments: Mapping[str, Any]) -> Path:
        STEP_SPECS[self.name].validate(arguments)
        return self.run(arguments)


class LegacyAlgorithmRepository:
    """One registry for the union of declared profiles; explicit selection when ambiguous."""

    def __init__(self, profiles: Sequence[str], commands: Mapping[CommandName, type[Command]]) -> None:
        if isinstance(profiles, str) or not profiles or len(set(profiles)) != len(profiles):
            raise ValueError("profiles must be a nonempty sequence of unique profile names")
        unknown = set(profiles) - ALGORITHM_PROFILES.keys()
        if unknown:
            raise ValueError(f"Unknown algorithm profiles: {sorted(unknown)}")
        expected = {command for profile in profiles for command in ALGORITHM_PROFILES[profile]}
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
        return ALGORITHM_PROFILES[self.select_profile(profile)]

    def run(
        self, name: CommandName | str, arguments: Mapping[str, Any], *, profile: str | None = None
    ) -> Path:
        selected = self.select_profile(profile)
        command_name = CommandName(name)
        if command_name not in ALGORITHM_PROFILES[selected]:
            raise ValueError(f"{command_name.value} is not part of the {selected} algorithm profile")
        return self.commands[command_name]()(arguments)
