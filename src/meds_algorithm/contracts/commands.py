"""Step specifications derived from profile interfaces and typed request fields.

The same derived specifications serve manifest validation and command inspection.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import MISSING, dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from ..algorithms import profile_classes, request_type
from ..artifacts.references import ArtifactReference
from ..requests import PredictionIndex, StepRequest, TrainingLabels
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

    @classmethod
    def from_request_type(cls, request_type: type[StepRequest]) -> StepSpec:
        """Derive the executable specification from a concrete request class."""
        artifacts = []
        external = []
        requires_splits = False
        label_access = "none"
        task_conditioned = False
        for field, kind in request_type.argument_fields():
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
        return cls(
            request_type.result_type.kind,
            request_type.output_argument,
            tuple(artifacts),
            tuple(external),
            requires_splits,
            label_access,
            task_conditioned,
        )

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


ALGORITHM_PROFILES = MappingProxyType(
    {cls.profile: tuple(CommandName(step) for step in cls.steps) for cls in profile_classes()}
)
STEP_SPECS = MappingProxyType(
    {
        step: StepSpec.from_request_type(request_type(profile, step))
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
