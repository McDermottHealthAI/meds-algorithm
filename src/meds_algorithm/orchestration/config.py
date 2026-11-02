"""Shared Hydra schema; algorithm configuration remains owned by the algorithm class."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunInputs:
    meds_dir: str | None = None
    labels_dir: str | None = None
    index_dir: str | None = None
    embedding_index_dir: str | None = None
    predicates_file: str | None = None
    task_predicates_file: str | None = None
    task_criteria_file: str | None = None
    evaluation_labels_dir: str | None = None
    context_labels_dir: str | None = None
    context_splits: list[str] = field(default_factory=list)


@dataclass
class Resources:
    timeout_min: int = 60
    cpus_per_task: int = 4
    mem_gb: int = 16
    gpus_per_node: int = 0
    partition: str | None = None
    account: str | None = None
    qos: str | None = None

    def validate(self):
        for name in ("timeout_min", "cpus_per_task", "mem_gb"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"resources.{name} must be a positive integer")
        if type(self.gpus_per_node) is not int or self.gpus_per_node < 0:
            raise ValueError("resources.gpus_per_node must be a nonnegative integer")


@dataclass
class RunResources:
    cpu: Resources = field(default_factory=Resources)
    compute: Resources = field(default_factory=Resources)
    steps: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class RunConfig:
    profile: str = "???"
    execution: str = "local"
    output_dir: str = "???"
    inputs: RunInputs = field(default_factory=RunInputs)
    algorithm: dict[str, Any] = field(default_factory=dict)
    stages: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    prediction_splits: list[str] = field(default_factory=lambda: ["held_out"])
    embedding_splits: list[str] = field(default_factory=lambda: ["train", "tuning", "held_out"])
    seed: int = 0
    resources: RunResources = field(default_factory=RunResources)
