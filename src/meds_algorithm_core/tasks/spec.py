"""The zero-shot task boundary: task specification, label-blind index, and relaxation ledger.

A supervised algorithm learns *what* to predict from labels. A zero-shot algorithm is never shown labels,
so the task definition itself must cross the contract boundary. The task language is ACES: a criteria
file plus, optionally, a dataset predicates file.

The contract fixes only the inputs (task, index, MEDS data), the final predictions, the semantics digest
that ties every artifact to the exact task it answers, and a minimal ledger of how the answered task
differs from the requested one. How a algorithm turns the task into predictions is its own; the
implementation guide recommends an encode -> infer -> decode shape.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

INDEX_COLUMNS = ("subject_id", "prediction_time")
RELAXATIONS_FILENAME = "relaxations.yaml"
PREDICTED_PROBABILITY = "predicted_boolean_probability"


def _digest_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


@dataclass(frozen=True)
class TaskSpec:
    """A task in the overall task language: an ACES criteria file and its optional predicates file."""

    criteria_file: Path
    predicates_file: Path | None = None
    name: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "criteria_file", Path(self.criteria_file))
        if self.predicates_file is not None:
            object.__setattr__(self, "predicates_file", Path(self.predicates_file))
        for path in (self.criteria_file, self.predicates_file):
            if path is not None and not path.is_file():
                raise FileNotFoundError(f"Task file {path} does not exist")

    @classmethod
    def from_arguments(cls, arguments: Mapping[str, Any]) -> TaskSpec:
        """Read the standard ``external_task_criteria_file`` / ``external_predicates_file`` arguments."""
        criteria = arguments.get("external_task_criteria_file")
        if not criteria:
            raise ValueError(
                "zero-shot commands require external_task_criteria_file=<ACES task YAML>; without it the "
                "algorithm cannot know what to predict"
            )
        return cls(
            criteria_file=criteria,
            predicates_file=arguments.get("external_predicates_file") or None,
            name=arguments.get("task_name") or None,
        )

    def semantics_digest(self) -> str:
        """A digest of exactly what was asked: the criteria bytes and the predicates bytes.

        Artifacts may be combined only when their semantics digests agree. The digest changes when either
        file changes, including when the same criteria are bound to another dataset's predicates.
        """
        digest = hashlib.sha256()
        for label, path in (("criteria", self.criteria_file), ("predicates", self.predicates_file)):
            digest.update(label.encode())
            digest.update(b"\0" if path is None else hashlib.sha256(path.read_bytes()).digest())
        return f"sha256:{digest.hexdigest()}"

    def provenance(self) -> dict[str, Any]:
        """The manifest ``inputs`` entry recording which task was answered."""

        def entry(path: Path | None) -> dict[str, str] | None:
            return None if path is None else {"path": str(path.resolve()), "digest": _digest_file(path)}

        return {
            "name": self.name,
            "criteria_file": entry(self.criteria_file),
            "predicates_file": entry(self.predicates_file),
        }


@dataclass(frozen=True)
class RelaxationLedger:
    """What a zero-shot prediction actually estimates, written as ``relaxations.yaml``.

    Only ``query_language``, ``decoded_quantity``, and ``exact`` are required. ``steps`` is free-form: one
    mapping per rewrite or assumption between the requested and the answered task. The implementation
    guide recommends ``name``, ``kind``, ``direction``, and ``detail`` keys; the contract does not validate
    them. An exact algorithm writes ``exact: true`` and no steps.
    """

    query_language: str
    decoded_quantity: str
    exact: bool
    steps: Sequence[Mapping[str, Any]] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for name in ("query_language", "decoded_quantity"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{RELAXATIONS_FILENAME} requires a non-empty {name}")
        if not isinstance(self.exact, bool):
            raise ValueError(f"{RELAXATIONS_FILENAME} requires exact: true or false")
        object.__setattr__(self, "steps", tuple(dict(step) for step in self.steps))

    def write(self, directory: Path | str) -> Path:
        path = Path(directory) / RELAXATIONS_FILENAME
        value = {
            "query_language": self.query_language,
            "decoded_quantity": self.decoded_quantity,
            "exact": self.exact,
            "steps": [dict(step) for step in self.steps],
        }
        path.write_text(yaml.safe_dump(value, sort_keys=False))
        return path

    @classmethod
    def read(cls, directory: Path | str) -> RelaxationLedger:
        path = Path(directory) / RELAXATIONS_FILENAME
        if not path.is_file():
            raise FileNotFoundError(f"{directory} has no {RELAXATIONS_FILENAME}")
        value = yaml.safe_load(path.read_text()) or {}
        missing = {"query_language", "decoded_quantity", "exact"} - set(value)
        if missing:
            raise ValueError(f"{path} lacks required fields {sorted(missing)}")
        return cls(
            query_language=value["query_language"],
            decoded_quantity=value["decoded_quantity"],
            exact=value["exact"],
            steps=value.get("steps") or (),
        )
