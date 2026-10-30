"""Record the caller's algorithm checkout; never infer it from the core package or cwd."""

import subprocess
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
