"""Install this repository's descriptor into a MEDS-DEV checkout."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

from ..artifacts.publication import staged_directory


def register(repo: Path, meds_dev: Path, name: str, profile: str | None = None) -> Path:
    source = repo.resolve()
    descriptors = {p.parent.name: p for p in (source / "algorithms").glob("*/model.yaml")}
    if profile is None:
        if len(descriptors) != 1:
            raise ValueError("Select --profile when the repository has several descriptors")
        profile = next(iter(descriptors))
    if profile not in descriptors:
        raise ValueError(f"No descriptor for {profile!r}; available: {sorted(descriptors)}")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
        raise ValueError("name must be a single alphanumeric, underscore or hyphen identifier")
    target = meds_dev.resolve() / "src" / "MEDS_DEV" / "models" / f"{name}__{profile}"
    if not target.parent.is_dir():
        raise FileNotFoundError(f"{meds_dev} has no src/MEDS_DEV/models directory")
    requirements = (source / "requirements.txt").read_text()
    # A file URL needs no quoting: uv reads quotes in requirement files literally, and pip splits on spaces.
    requirements = (
        "\n".join(
            f"-e {source.as_uri()}" if line.strip() == "-e ." else line for line in requirements.splitlines()
        )
        + "\n"
    )
    with staged_directory(target) as staging:
        shutil.copy2(descriptors[profile], staging / "model.yaml")
        (staging / "requirements.txt").write_text(requirements)
        predicates = source / "predicates.yaml"
        if predicates.is_file():
            shutil.copy2(predicates, staging / "predicates.yaml")
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--meds-dev", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--name", required=True)
    parser.add_argument("--profile")
    args = parser.parse_args()
    print(register(args.repo, args.meds_dev, args.name, args.profile))
