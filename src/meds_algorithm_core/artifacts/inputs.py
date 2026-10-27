"""Expose an upstream artifact reference as an explicit orchestration argument."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..contracts.commands import STEP_SPECS, CommandName
from .manifest import read_manifest


def resolve_input(artifact: Path, argument: str) -> Path:
    """Resolve a producer's recorded input; validate the referenced envelope type."""
    manifest = read_manifest(artifact)
    spec = STEP_SPECS[CommandName(manifest["command"]["name"])]
    expected = next((item for item in spec.artifact_inputs if item.argument == argument), None)
    if expected is None:
        raise ValueError(f"{argument!r} is not an artifact input of this producer")
    entry = manifest.get("inputs", {}).get(argument)
    if not isinstance(entry, dict) or not entry.get("path"):
        raise ValueError(f"Producer must record inputs.{argument}.path")
    path = Path(entry["path"])
    if not path.is_absolute():
        path = artifact.resolve() / path
    path = path.resolve()
    upstream = read_manifest(path)
    if upstream["artifact"]["type"] != expected.artifact_type.value:
        raise ValueError(f"{argument} has the wrong artifact type")
    # Content, vocabulary, and algorithm-specific compatibility are still checked by the consumer.
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("argument")
    args = parser.parse_args()
    print(resolve_input(args.artifact, args.argument))
