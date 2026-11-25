"""Record the caller's algorithm checkout; never infer it from the core package or cwd."""

import json
import subprocess
from importlib import metadata
from pathlib import Path
from typing import Any


def code_provenance(repo: Path | str | None) -> dict[str, Any]:
    unknown = {
        "repository": None if repo is None else str(Path(repo).resolve()),
        "git_commit": None,
        "dirty": None,
    }
    if repo is None:
        return unknown
    root = Path(repo).resolve()
    # Do not accidentally attribute an unpacked wheel to an enclosing unrelated checkout.
    if not (root / ".git").exists():
        return unknown

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    try:
        commit = git("rev-parse", "HEAD")
        status = git("status", "--porcelain")
    except (OSError, subprocess.CalledProcessError):
        return unknown
    return {"repository": str(root), "git_commit": commit, "dirty": bool(status)}


def distribution_provenance(module: str) -> dict[str, Any] | None:
    """The installed distribution providing ``module``'s top-level package.

    Returns ``{"name", "version", "editable"}``, or ``None`` when no installed distribution provides it (e.g.
    code run from a source tree without installing). An editable install points at mutable source, so its
    version does not identify the code that runs.
    """
    names = metadata.packages_distributions().get(module.split(".")[0])
    if not names:
        return None
    distribution = metadata.distribution(sorted(names)[0])
    direct_url = distribution.read_text("direct_url.json")
    editable = bool(direct_url and json.loads(direct_url).get("dir_info", {}).get("editable"))
    return {"name": distribution.metadata["Name"], "version": distribution.version, "editable": editable}
