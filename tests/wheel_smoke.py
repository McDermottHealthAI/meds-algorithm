"""Run with only the installed base wheel; never add source or optional dependencies to sys.path."""

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

from meds_model_core import measured_artifact, read_manifest
from meds_model_core.spec import specification

assert importlib.util.find_spec("polars") is None
assert importlib.util.find_spec("pytest") is None
assert specification().splitlines()[0] == "# MEDS Model Repository Contract, version 3"
with tempfile.TemporaryDirectory() as directory:
    artifact = Path(directory) / "artifact"
    with measured_artifact(
        artifact,
        artifact_type="patients",
        command="preprocess_data",
        producer="wheel.smoke",
        payload_format="smoke/v1",
    ) as staging:
        (staging / "payload").write_text("ok")
    manifest = read_manifest(artifact)
    assert manifest["code"]["git_commit"] is None and manifest["code"]["dirty"] is None
    assert (artifact / "payload").read_text() == "ok"
for name in ("meds-model-core-spec", "meds-model-resolve-input", "meds-model-add-to-meds-dev"):
    executable = Path(sys.executable).parent / (name + (".exe" if sys.platform == "win32" else ""))
    subprocess.run([str(executable), "--help"], check=True, capture_output=True)
print(
    "Base wheel: artifact publication, unknown provenance, specification, CLIs and optional imports verified"
)
