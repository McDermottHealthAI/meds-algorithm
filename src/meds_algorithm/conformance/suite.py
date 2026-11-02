"""Opt-in inherited pytest suite for concrete algorithm repositories.

Subclass AlgorithmConformanceTests in a test module. Provide session-scoped
algorithm_case and profile fixtures, parametrizing profile from the repository.
Importing this module does not register a plugin or collect tests automatically.
"""

import os
import subprocess

import pytest
import yaml

from meds_algorithm import ALGORITHM_PROFILES, read_manifest
from meds_algorithm.integrations.meds_dev import register

from . import meds_dev as integration
from .assertions import assert_prediction_keys, read_predictions
from .cases import AlgorithmCase
from .end_to_end import assert_profile_run
from .reports import assert_implementation_report


class AlgorithmConformanceTests:
    """Eight shared acceptance checks, executed against the downstream algorithm."""

    @pytest.fixture
    def completed_profile(self, algorithm_case: AlgorithmCase, profile):
        assert profile in algorithm_case.profiles, f"Unregistered profile: {profile}"
        if profile in algorithm_case.stub_profiles:
            pytest.skip(f"algorithm_stub: implement {profile} and its execution adapters")
        return profile

    @pytest.fixture(scope="session")
    def meds_dev(self, request, tmp_path_factory, algorithm_case: AlgorithmCase):
        completed = set(algorithm_case.profiles) - set(algorithm_case.stub_profiles)
        if not completed:
            pytest.skip("algorithm_stub: MEDS-DEV runs only after a profile is implemented")
        return integration.provision_meds_dev(
            request,
            tmp_path_factory,
            task_criteria=any(profile.startswith("zero_shot_") for profile in completed),
        )

    def test_profile_implementations_match_contract(self, algorithm_case: AlgorithmCase, profile):
        repository = algorithm_case.create_repository()
        assert repository.profile_commands(profile) == ALGORITHM_PROFILES[profile]

    def test_algorithm_configuration_roundtrips(self, algorithm_case: AlgorithmCase, tmp_path):
        for index, config in enumerate(algorithm_case.configurations):
            path = config.save(tmp_path / f"config-{index}.json")
            assert type(config).load(path) == config

    def test_end_to_end(self, algorithm_case: AlgorithmCase, completed_profile, tmp_path):
        result = algorithm_case.run_e2e(tmp_path / "run", profile=completed_profile, seed=0)
        assert_profile_run(
            result,
            profile=completed_profile,
            run_e2e=algorithm_case.run_e2e,
            fitted_codes=algorithm_case.fitted_codes,
            tmp_path=tmp_path,
        )

    def test_completed_algorithm_has_a_completed_report(self, algorithm_case: AlgorithmCase):
        report = (algorithm_case.root / "IMPLEMENTATION_REPORT.md").read_text(encoding="utf-8")
        assert_implementation_report(report, algorithm_case.profiles, algorithm_case.stub_profiles)

    def test_algorithm_yaml_is_a_meds_dev_descriptor(self, algorithm_case: AlgorithmCase, profile):
        descriptor = yaml.safe_load(
            (algorithm_case.root / "algorithms" / profile / "model.yaml").read_text(encoding="utf-8")
        )
        assert set(descriptor) == {"metadata", "commands"}
        assert "supervised" in descriptor["commands"]
        assert descriptor["commands"]["supervised"]["predict"]

    def test_slurm_dry_run_is_non_mutating(self, algorithm_case: AlgorithmCase, profile):
        root = algorithm_case.root
        before = {path.relative_to(root) for path in root.rglob("*")}
        result = subprocess.run(
            ["bash", "slurm/submit.sh", "--dry-run"],
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
            timeout=60,
            env={
                **os.environ,
                "MEDS_ROOT": "/example/meds",
                "LABELS_DIR": "/example/labels",
                "INDEX_DIR": "/example/index",
                "TASK_CRITERIA_FILE": "/example/task.yaml",
                "PREDICATES_FILE": "/example/predicates.yaml",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PROFILE": profile,
                "STAGES": ",".join(step.value for step in ALGORITHM_PROFILES[profile]),
            },
        )
        assert before == {path.relative_to(root) for path in root.rglob("*")}
        for command in ALGORITHM_PROFILES[profile]:
            assert command.value in result.stdout
        assert "sbatch" in result.stdout

    @pytest.mark.slow
    @pytest.mark.meds_dev
    def test_meds_dev_runs_algorithm_yaml(
        self, algorithm_case: AlgorithmCase, completed_profile, meds_dev, tmp_path
    ):
        registered = register(algorithm_case.root, meds_dev, algorithm_case.name, completed_profile)
        assert (registered / "model.yaml").is_file()
        prepared = algorithm_case.prepare_meds_dev_run(meds_dev, tmp_path, profile=completed_profile)
        integration.run(
            [integration.venv_bin(meds_dev) / "meds-dev-model", f"model={registered.name}", *prepared.args],
            timeout=integration.RUN_TIMEOUT,
        )
        self.assert_predictions(prepared.predictions_dir, prepared.labels_dir, prepared.splits)
        manifest = read_manifest(prepared.predictions_dir)
        memory = manifest["resources"]["memory"]
        if memory["source"] == "unavailable":
            assert memory["peak_process_tree_rss_bytes"] is None
        else:
            assert memory["peak_process_tree_rss_bytes"] > 0

    @pytest.mark.slow
    @pytest.mark.real_data
    def test_full_dag_on_mimic_iv_demo(
        self, algorithm_case: AlgorithmCase, completed_profile, meds_dev, tmp_path
    ):
        dataset_dir, labels_dir, predicates_file = integration.prepare_mimic_demo(meds_dev, tmp_path)
        assert dataset_dir.is_dir() and labels_dir.exists()
        assert predicates_file.is_file(), "reuse MEDS-DEV's MIMIC-IV predicates"
        inputs = {}
        if completed_profile.startswith("zero_shot_"):
            inputs["external_task_criteria_file"] = integration.mimic_task_criteria(meds_dev)
        result = algorithm_case.run_e2e(
            tmp_path / "mimic-run",
            profile=completed_profile,
            external_meds_dir=dataset_dir,
            external_labels_dir=labels_dir,
            external_predicates_file=predicates_file,
            splits=["held_out"],
            **inputs,
        )
        assert list(result.artifacts) == [step.value for step in ALGORITHM_PROFILES[completed_profile]]
        predictions_dir = result.artifacts[ALGORITHM_PROFILES[completed_profile][-1].value]
        self.assert_predictions(predictions_dir, labels_dir, ["held_out"])

    @staticmethod
    def assert_predictions(directory, labels_dir, splits):
        """One validation path for both integration tests, including sharded outputs."""
        predictions = read_predictions(directory)
        assert predictions.height > 0
        assert_prediction_keys(directory, labels_dir, splits)
        assert read_manifest(directory)["artifact"]["type"] == "predictions"
