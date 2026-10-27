import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest
import yaml

from meds_algorithm_core import measured_artifact, read_manifest, write_run_result
from meds_algorithm_core.artifacts.inputs import resolve_input
from meds_algorithm_core.artifacts.publication import staged_directory
from meds_algorithm_core.runtime.provenance import code_provenance
from meds_algorithm_core.runtime.resources import _ProcessTreeMemorySampler


def publish(path, **kwargs):
    return measured_artifact(
        path,
        artifact_type="patients",
        command="preprocess_data",
        producer="test.algorithm",
        payload_format="test/v1",
        **kwargs,
    )


def test_body_failure_and_existing_destination_preserve_previous_artifact(tmp_path):
    target = tmp_path / "artifact"
    with publish(target) as staging:
        (staging / "payload").write_text("old")
    with pytest.raises(FileExistsError), publish(target):
        pytest.fail("existing artifact must be rejected before algorithm work")
    with pytest.raises(RuntimeError, match="algorithm failed"), publish(target, overwrite=True) as staging:
        (staging / "payload").write_text("new")
        raise RuntimeError("algorithm failed")
    assert (target / "payload").read_text() == "old"
    assert not list(tmp_path.glob(".*.staging-*"))
    assert not list(tmp_path.glob("*.lock"))


@pytest.mark.parametrize("restore_fails", [False, True])
def test_publication_failure_retains_old_artifact(tmp_path, monkeypatch, restore_fails):
    target = tmp_path / "artifact"
    target.mkdir()
    (target / "old").write_text("valuable")
    replace = Path.replace

    def fail_new(source, destination):
        if ".staging-" in source.name or (restore_fails and ".backup-" in source.name):
            raise OSError("injected rename failure")
        return replace(source, destination)

    monkeypatch.setattr(Path, "replace", fail_new)
    with pytest.raises((OSError, RuntimeError)), publish(target, overwrite=True) as staging:
        (staging / "new").write_text("candidate")
    copies = list(tmp_path.rglob("old"))
    assert len(copies) == 1 and copies[0].read_text() == "valuable"
    assert (copies[0].parent == target) is not restore_fails


def test_unique_staging_and_exclusive_destination_lock(tmp_path):
    target = tmp_path / "artifact"
    with staged_directory(target) as first:
        with pytest.raises(FileExistsError, match="locked"), staged_directory(target, overwrite=True):
            pass
        with staged_directory(tmp_path / "different") as other:
            assert first != other and first.exists()
    with staged_directory(target, overwrite=True) as second:
        assert first != second


def test_manifest_write_failure_keeps_previous_artifact(tmp_path, monkeypatch):
    target = tmp_path / "artifact"
    target.mkdir()
    (target / "old").touch()
    monkeypatch.setattr(yaml, "safe_dump", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("yaml")))
    with pytest.raises(ValueError, match="yaml"), publish(target, overwrite=True):
        pass
    assert (target / "old").is_file()


def test_algorithm_provenance_is_explicit_and_unknown_outside_checkout(tmp_path, monkeypatch):
    algorithm = tmp_path / "algorithm"
    algorithm.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(algorithm), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "--allow-empty",
        "-m",
        "algorithm",
    )
    monkeypatch.chdir(tmp_path)
    with publish(tmp_path / "artifact", repo=algorithm):
        pass
    code = read_manifest(tmp_path / "artifact")["code"]
    assert code["git_commit"] == git("rev-parse", "HEAD") and code["dirty"] is False
    (algorithm / "changed").touch()
    assert code_provenance(algorithm)["dirty"] is True
    assert code_provenance(None)["git_commit"] is None
    assert code_provenance(algorithm / "unpacked-wheel")["dirty"] is None


@pytest.mark.skipif(sys.platform != "linux", reason="Linux /proc behavior")
def test_process_tree_includes_worker_thread_children():
    ready = threading.Event()
    stop = threading.Event()
    children = []

    def worker():
        with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]) as child:
            children.append(child.pid)
            ready.set()
            try:
                stop.wait(10)
            finally:
                child.terminate()
                child.wait(timeout=5)

    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert ready.wait(5)
        assert children[0] in _ProcessTreeMemorySampler._process_tree(os.getpid())
    finally:
        stop.set()
        thread.join(timeout=10)


def test_unavailable_resource_measurement_is_reported_honestly(monkeypatch):
    from meds_algorithm_core.runtime import resources

    monkeypatch.setattr(resources, "resource", None)
    sampler = _ProcessTreeMemorySampler()
    sampler.source = "getrusage"
    sampler.start()
    sampler.stop()
    assert sampler.source == "unavailable" and sampler.peak_rss_bytes is None
    assert not sampler.includes_descendants


def test_upstream_resolution_and_result_identity(tmp_path):
    data = tmp_path / "data"
    with publish(data):
        pass
    algorithm = tmp_path / "algorithm"
    with measured_artifact(
        algorithm,
        artifact_type="supervised_algorithm",
        command="train_supervised",
        producer="test",
        payload_format="test/v1",
        inputs={"input_data_dir": {"path": "../data"}},
    ):
        pass
    assert resolve_input(algorithm, "input_data_dir") == data
    with pytest.raises(ValueError, match="disagrees"):
        write_run_result(
            tmp_path / "run",
            repo=tmp_path,
            profile="supervised",
            artifacts={"train_supervised": data},
            dataset={},
            task={},
        )


def test_invalid_manifest_and_publication_type_fail_before_use(tmp_path):
    target = tmp_path / "artifact"
    with publish(target):
        pass
    path = target / "manifest.yaml"
    value = yaml.safe_load(path.read_text())
    value["artifact"]["type"] = "predictions"
    path.write_text(yaml.safe_dump(value))
    with pytest.raises(ValueError, match="does not match"):
        read_manifest(target)
    with (
        pytest.raises(ValueError, match="does not match"),
        measured_artifact(
            tmp_path / "new",
            artifact_type="predictions",
            command="preprocess_data",
            producer="test",
            payload_format="test/v1",
        ),
    ):
        pytest.fail("must reject type before algorithm work")
