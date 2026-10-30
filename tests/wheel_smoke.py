"""Run with only the installed base wheel; never add source or optional dependencies to sys.path."""

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

from meds_algorithm_core import NNConfig, measured_artifact, read_manifest
from meds_algorithm_core.spec import architecture, specification

assert importlib.util.find_spec("polars") is None
assert importlib.util.find_spec("pytest") is None
assert specification().splitlines()[0] == "# MEDS Algorithm Repository Contract, version 4"
assert "classDiagram" in architecture() and "StepRunner" in architecture()
with tempfile.TemporaryDirectory() as directory:
    config = NNConfig(capacity=0.5, learning_rate=0.001, batch_size=16)
    assert NNConfig.load(config.save(Path(directory) / "config.json")) == config
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
for name in ("meds-algorithm-core-spec", "meds-algorithm-resolve-input", "meds-algorithm-add-to-meds-dev"):
    executable = Path(sys.executable).parent / (name + (".exe" if sys.platform == "win32" else ""))
    subprocess.run([str(executable), "--help"], check=True, capture_output=True)
print(
    "Base wheel: artifact publication, unknown provenance, specification, CLIs and optional imports verified"
)
