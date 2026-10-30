"""Unique staging, exclusive writers, and recoverable directory replacement.

New artifacts appear by one rename. Overwrite uses two renames and can briefly hide the
destination from readers. A process crash may leave the backup/lock for manual recovery;
we never silently delete another writer's staging area or a previous artifact.
"""

import os
import shutil
import tempfile
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


@contextmanager
def staged_directory(destination: Path | str, *, overwrite: bool = False) -> Iterator[Path]:
    destination = Path(destination).absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.with_name(f".{destination.name}.lock")
    # Atomic acquisition also serializes writers in different threads/processes.
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise FileExistsError(
            f"Artifact is locked: {lock}; inspect the writer before recovering a stale lock"
        ) from error
    staging = None
    backup = None
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(f"pid={os.getpid()}\n")
        if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
            raise ValueError(f"Artifact destination must be a directory, not a file/symlink: {destination}")
        if destination.exists() and not overwrite:
            raise FileExistsError(f"{destination} already exists; pass overwrite=true to replace it")
        staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=destination.parent))
        yield staging
        if destination.exists():
            backup = destination.with_name(f".{destination.name}.backup-{uuid4().hex}")
            destination.replace(backup)
        try:
            staging.replace(destination)
        except BaseException as publish_error:
            if backup is not None:
                try:
                    backup.replace(destination)
                except BaseException as restore_error:
                    raise RuntimeError(
                        f"Publication failed; previous artifact is preserved at {backup}; "
                        f"restore also failed: {restore_error}"
                    ) from publish_error
            raise
        if backup is not None:
            try:
                shutil.rmtree(backup)
            except OSError as error:
                warnings.warn(
                    f"Published {destination}; retained old backup {backup}: {error}",
                    RuntimeWarning,
                    stacklevel=2,
                )
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        lock.unlink(missing_ok=True)
