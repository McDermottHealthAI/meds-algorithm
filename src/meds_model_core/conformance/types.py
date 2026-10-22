from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class E2EResult:
    """Artifacts plus the requested evaluation index used to verify prediction keys."""

    artifacts: Mapping[str, Path]
    labels_dir: Path
    splits: Sequence[str]
    # The external inputs passed to the commands. Zero-shot profiles MUST include external_task_criteria_file
    # (and external_predicates_file when used) so tests can check which task each artifact answers.
    inputs: Mapping[str, Any] = field(default_factory=dict)
    # Codes added by conformance.signal.add_split_canaries to tuning and held-out subjects.
    canaries: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MEDSDevRun:
    """MEDS-DEV invocation plus the evaluation index its predictions must cover."""

    args: Sequence[str]
    predictions_dir: Path
    labels_dir: Path
    splits: Sequence[str]
