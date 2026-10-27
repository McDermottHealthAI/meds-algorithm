"""Measured artifacts with explicit algorithm provenance and rollback-safe replacement."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml

from ..contracts.commands import STEP_SPECS, CommandName
from ..runtime.provenance import code_provenance
from ..runtime.resources import _ProcessTreeMemorySampler
from ..version import CONTRACT_VERSION
from .publication import staged_directory


def read_manifest(directory: Path | str) -> dict[str, Any]:
    path = Path(directory) / "manifest.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Artifact {directory} has no manifest.yaml")
    value = yaml.safe_load(path.read_text())
    if not isinstance(value, dict) or value.get("contract_version") != CONTRACT_VERSION:
        raise ValueError(f"{path} is not a version 4 MEDS algorithm artifact manifest")
    for field in ("artifact", "command", "code", "inputs", "resources"):
        if not isinstance(value.get(field), dict):
            raise ValueError(f"{path} requires a {field} mapping")
    try:
        spec = STEP_SPECS[CommandName(value["command"]["name"])]
    except (KeyError, ValueError) as error:
        raise ValueError(f"{path} has an unknown or missing command") from error
    if value["artifact"].get("type") != spec.artifact_type.value:
        raise ValueError(f"{path} artifact type does not match its command")
    for field in ("producer", "payload_format"):
        if not isinstance(value["artifact"].get(field), str) or not value["artifact"][field].strip():
            raise ValueError(f"{path} requires artifact.{field}")
    return value


def digest_file(path: Path | str) -> str:
    with Path(path).open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return f"sha256:{digest}"


def digest_config(config: Any) -> str:
    """Digest a command's configuration: its arguments plus any algorithm-owned settings it resolved.

    The value is canonical JSON (sorted keys; paths and other objects as strings), so the same arguments
    always give the same digest regardless of order.
    """
    canonical = json.dumps(config, sort_keys=True, default=str, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"


@contextmanager
def measured_artifact(
    destination: Path | str,
    *,
    artifact_type: str,
    command: str,
    producer: str,
    payload_format: str | Callable[[], str],
    inputs: dict[str, Any] | None = None,
    config_digest: str | None = None,
    semantics_digest: str | None = None,
    external_predicates_file: Path | str | None = None,
    overwrite: bool = False,
    repo: Path | str | None = None,
    manifest_fields: dict[str, Any] | None = None,
) -> Iterator[Path]:
    """Measure staged output and publish its manifest with rollback on replacement failure."""
    if STEP_SPECS[CommandName(command)].artifact_type.value != artifact_type:
        raise ValueError("Artifact type does not match its command")
    if (
        not isinstance(producer, str)
        or not producer.strip()
        or (
            not callable(payload_format)
            and (not isinstance(payload_format, str) or not payload_format.strip())
        )
    ):
        raise ValueError("producer and payload_format must be nonempty strings")
    with staged_directory(destination, overwrite=overwrite) as staging:
        started = time.monotonic()
        sampler = _ProcessTreeMemorySampler()
        sampler.start()
        try:
            yield staging
        finally:
            sampler.stop()
        resolved_format = payload_format() if callable(payload_format) else payload_format
        if not isinstance(resolved_format, str) or not resolved_format.strip():
            raise ValueError("payload_format must resolve to a nonempty string")
        predicates = None
        if external_predicates_file is not None:
            predicates = {
                "path": str(Path(external_predicates_file).resolve()),
                "digest": digest_file(external_predicates_file),
            }
        recorded_inputs = dict(inputs or {})
        if predicates is not None:
            recorded_inputs["external_predicates_file"] = predicates
        manifest = {
            "contract_version": CONTRACT_VERSION,
            "artifact": {
                "type": artifact_type,
                "payload_format": resolved_format,
                "producer": producer,
            },
            "command": {"name": command, "config_digest": config_digest},
            "code": code_provenance(repo),
            "inputs": recorded_inputs,
            "semantics_digest": semantics_digest,
            "resources": {
                "wall_seconds": time.monotonic() - started,
                "memory": {
                    "peak_process_tree_pss_bytes": sampler.peak_pss_bytes,
                    "peak_process_tree_rss_bytes": sampler.peak_rss_bytes,
                    "sampling_interval_seconds": sampler.interval_seconds,
                    "source": sampler.source,
                    "includes_descendants": sampler.includes_descendants,
                },
                "gpu": {
                    "peak_allocated_bytes": None,
                    "peak_reserved_bytes": None,
                    "source": None,
                },
                "measurement": {
                    "schema_version": "1",
                },
            },
        }
        if manifest_fields:
            if manifest.keys() & manifest_fields.keys():
                raise ValueError("Extra manifest fields cannot replace the common envelope")
            manifest.update(manifest_fields)
        (staging / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))
