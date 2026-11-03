"""Plan all six profiles, then exercise real subprocesses and Submitit serialization."""

import json
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from meds_algorithm import ALGORITHM_PROFILES, AlgorithmConfig, AlgorithmRepository, measured_artifact
from meds_algorithm.algorithms import profile_class
from meds_algorithm.orchestration.cli import compose_run, main
from meds_algorithm.orchestration.config import RunConfig, RunInputs
from meds_algorithm.orchestration.execution import RunCoordinator, StageJob
from meds_algorithm.orchestration.planning import RunPlanner


@dataclass(frozen=True)
class ExampleConfig(AlgorithmConfig):
    rate: float = 0.1


@pytest.fixture
def setup(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    implementations = {}
    for profile in ALGORITHM_PROFILES:
        parent = profile_class(profile)
        implementations[profile] = type(
            "Example",
            (parent,),
            {
                "config_type": ExampleConfig,
                **{
                    name: lambda *args: pytest.fail("planning must not execute algorithm code")
                    for name in parent.__abstractmethods__
                },
            },
        )
    repository = AlgorithmRepository(implementations, repo=repo)
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    for name in ("criteria.yaml", "predicates.yaml"):
        (inputs / name).write_text("predicates: {}\n")
    config = RunConfig(
        profile="supervised",
        output_dir=str(tmp_path / "run"),
        inputs=RunInputs(
            meds_dir=str(inputs),
            labels_dir=str(inputs),
            index_dir=str(inputs),
            task_criteria_file=str(inputs / "criteria.yaml"),
            predicates_file=str(inputs / "predicates.yaml"),
        ),
    )
    # A real child program checks the same JSON arguments as generated CLIs and leaves observable evidence.
    script = repo / "worker.py"
    script.write_text("""import json, os, sys
from pathlib import Path
step = sys.argv[1]
args = dict(item.split("=", 1) for item in sys.argv[4:])
args = {key: json.loads(value) for key, value in args.items()}
cfg = json.loads(Path(args["config_file"]).read_text())
assert cfg["values"]["rate"] == 0.1
for key, value in args.items():
    if key.startswith("input_"):
        assert Path(value).is_dir(), value
output = Path(next(value for key,value in args.items() if key.startswith("output_")))
output.mkdir(parents=True)
(output / "pid.txt").write_text(str(os.getpid()))
print(step, flush=True)
""")
    planner = RunPlanner(repository, command=(sys.executable, str(script)), base_dir=tmp_path)
    return SimpleNamespace(repo=repo, repository=repository, config=config, planner=planner, inputs=inputs)


@pytest.mark.parametrize("profile", list(ALGORITHM_PROFILES))
def test_all_profiles_resolve_typed_arguments_without_writing(setup, profile):
    before = set(setup.repo.parent.rglob("*"))
    config = replace(setup.config, profile=profile)
    plan = setup.planner.resolve(config)
    assert [stage.name for stage in plan.stages] == list(ALGORITHM_PROFILES[profile])
    for i, stage in enumerate(plan.stages):
        assert stage.depends_on == ((plan.stages[i - 1].name,) if i else ())
        assert stage.arguments["config_file"] == str(plan.output_dir / "algorithm.json")
        if stage.name in {"pretrain", "infer_embeddings", "infer_trajectories"}:
            assert "external_labels_dir" not in stage.arguments
            assert "external_task_criteria_file" not in stage.arguments
    assert plan.configuration["algorithm"]["rate"] == 0.1
    assert set(setup.repo.parent.rglob("*")) == before


def test_hydra_composition_interpolation_and_override_validation(setup):
    conf = setup.repo / "configs"
    conf.mkdir()
    (conf / "run.yaml").write_text("""defaults: [meds_run, _self_]
profile: supervised
output_dir: ${inputs.meds_dir}/../new-run
inputs:
  meds_dir: inputs
algorithm:
  rate: 0.2
""")
    config = compose_run(conf, "run", ["algorithm.rate=0.3", "resources.compute.gpus_per_node=1"])
    assert config.algorithm["rate"] == 0.3
    assert config.resources.compute.gpus_per_node == 1
    assert "${" not in config.output_dir
    with pytest.raises(Exception, match="typo"):
        compose_run(conf, "run", ["resources.compute.typo=1"])
    with pytest.raises(ValueError, match="Unknown fields"):
        setup.planner.resolve(replace(setup.config, algorithm={"typo": 1}))


def test_cli_dry_run_has_no_output_or_scheduler_side_effects(setup, monkeypatch, capsys):
    from dataclasses import asdict

    import yaml

    conf = setup.repo / "configs"
    conf.mkdir()
    (conf / "run.yaml").write_text(
        yaml.safe_dump({"defaults": ["meds_run", "_self_"], **asdict(setup.config)})
    )
    monkeypatch.setattr(RunCoordinator, "execute", lambda *args: pytest.fail("must not execute"))
    before = set(setup.repo.parent.rglob("*"))
    main(setup.repository, module="example", argv=["--config-dir", str(conf), "--dry-run", "execution=slurm"])
    plan = json.loads(capsys.readouterr().out)
    assert plan["execution"] == "slurm"
    assert plan["stages"][-1]["arguments"]["external_index_dir"] == str(setup.inputs)
    assert set(setup.repo.parent.rglob("*")) == before


def test_missing_inputs_and_invalid_resources_fail_before_execution(setup):
    with pytest.raises(ValueError, match="labels_dir"):
        setup.planner.resolve(replace(setup.config, inputs=RunInputs(meds_dir=str(setup.inputs))))
    with pytest.raises(ValueError, match="stages"):
        setup.planner.resolve(replace(setup.config, stages=["typo"]))
    setup.config.resources.compute.timeout_min = 0
    with pytest.raises(ValueError, match="timeout_min"):
        setup.planner.resolve(setup.config)
    assert not Path(setup.config.output_dir).exists()


def test_subset_requires_explicit_valid_reused_artifacts(setup):
    config = replace(setup.config, stages=["predict_supervised"])
    with pytest.raises(ValueError, match=r"artifacts\.input_data_dir"):
        setup.planner.resolve(config)
    for key, kind, step in (
        ("input_data_dir", "patients", "preprocess_data"),
        ("input_supervised_algorithm_dir", "supervised_algorithm", "train_supervised"),
    ):
        directory = setup.repo.parent / key
        with measured_artifact(
            directory, artifact_type=kind, command=step, producer="fixture", payload_format="test/v1"
        ):
            pass
        config.artifacts[key] = str(directory)
    plan = setup.planner.resolve(config)
    assert len(plan.stages) == 1
    assert plan.stages[0].depends_on == ()
    with pytest.raises(ValueError, match="Ambiguous"):
        setup.planner.resolve(replace(config, stages=[]))


def test_real_local_run_records_plan_logs_and_fresh_processes(setup):
    plan = setup.planner.resolve(setup.config)
    RunCoordinator().execute(plan)
    assert (
        json.loads((plan.output_dir / "plan.json").read_text())["configuration"]["algorithm"]["rate"] == 0.1
    )
    pids = {p.read_text() for p in (plan.output_dir / "artifacts").rglob("pid.txt")}
    assert len(pids) == 3
    for stage in plan.stages:
        assert stage.name in (plan.output_dir / "logs" / f"{stage.name}.log").read_text()
    with pytest.raises(FileExistsError):
        RunCoordinator().execute(plan)


def test_local_failure_stops_downstream_stages(setup):
    plan = setup.planner.resolve(setup.config)
    failing = replace(plan.stages[1], argv=(sys.executable, "-c", "raise RuntimeError('deliberate')"))
    plan = replace(plan, stages=(plan.stages[0], failing, plan.stages[2]))
    with pytest.raises(AssertionError, match="command failed"):
        RunCoordinator().execute(plan)
    assert not (plan.output_dir / "artifacts" / "predictions").exists()
    assert "deliberate" in (plan.output_dir / "logs" / "train_supervised.log").read_text()


def commit_repo(repo):
    for args in (
        ["init"],
        ["add", "."],
        [
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "fixture",
        ],
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def test_submitit_wires_resources_dependencies_receipts_and_cancellation(setup, monkeypatch):
    import submitit

    commit_repo(setup.repo)
    setup.config.resources.compute.gpus_per_node = 1
    setup.config.resources.steps["predict_supervised"] = {"mem_gb": 32}
    plan = setup.planner.resolve(replace(setup.config, execution="slurm"))
    calls, jobs = [], []

    class Executor:
        def __init__(self, **kwargs):
            assert kwargs["cluster"] == "slurm"

        def update_parameters(self, **kwargs):
            calls.append(kwargs)

        def submit(self, callable):
            assert isinstance(callable, StageJob)
            job = SimpleNamespace(job_id=str(len(jobs) + 1), cancel=lambda: None)
            jobs.append(job)
            return job

    monkeypatch.setattr(submitit, "AutoExecutor", Executor)
    RunCoordinator().execute(plan)
    assert "slurm_additional_parameters" not in calls[0]
    assert calls[1]["slurm_additional_parameters"] == {"dependency": "afterok:1"}
    assert calls[2]["slurm_additional_parameters"] == {"dependency": "afterok:2"}
    assert [c["gpus_per_node"] for c in calls] == [0, 1, 1]
    assert calls[2]["mem_gb"] == 32
    assert json.loads((plan.output_dir / "submission.json").read_text())["status"] == "submitted"
    cancelled = []

    def submit(self, callable):
        if jobs:
            raise RuntimeError("submission failed")
        job = SimpleNamespace(job_id="10", cancel=lambda: cancelled.append("10"))
        jobs.append(job)
        return job

    jobs.clear()
    monkeypatch.setattr(Executor, "submit", submit)
    failed_plan = setup.planner.resolve(
        replace(setup.config, execution="slurm", output_dir=str(setup.repo.parent / "failed"))
    )
    with pytest.raises(RuntimeError, match="submission failed"):
        RunCoordinator().execute(failed_plan)
    assert cancelled == ["10"]
    assert (
        json.loads((failed_plan.output_dir / "submission.json").read_text())["status"] == "submission_failed"
    )


def test_slurm_refuses_dirty_or_unknown_checkout(setup):
    plan = setup.planner.resolve(replace(setup.config, execution="slurm"))
    with pytest.raises(ValueError, match="clean committed"):
        RunCoordinator().execute(plan)

    assert not plan.output_dir.exists()
    commit_repo(setup.repo)
    plan = setup.planner.resolve(replace(setup.config, execution="slurm"))
    (setup.repo / "untracked").touch()
    with pytest.raises(ValueError, match="clean committed"):
        RunCoordinator().execute(plan)


def test_slurm_rejects_output_that_would_dirty_checkout(setup):
    commit_repo(setup.repo)
    plan = setup.planner.resolve(replace(setup.config, execution="slurm", output_dir=str(setup.repo / "run")))
    with pytest.raises(ValueError, match="Git-ignored"):
        RunCoordinator().execute(plan)
    assert not plan.output_dir.exists()


def test_probe_and_context_inputs_are_explicit(setup):
    embedding_index = setup.repo.parent / "embedding-index"
    embedding_index.mkdir()
    config = replace(
        setup.config,
        profile="probe",
        inputs=replace(setup.config.inputs, embedding_index_dir=str(embedding_index)),
    )
    plan = setup.planner.resolve(config)
    assert plan.stages[2].arguments["external_index_dir"] == str(embedding_index)
    assert plan.stages[2].arguments["splits"] == ["train", "tuning", "held_out"]
    assert plan.stages[-1].arguments["external_index_dir"] == str(setup.inputs)
    context = replace(
        setup.config,
        profile="predict_only",
        inputs=replace(setup.config.inputs, context_labels_dir=str(setup.inputs), context_splits=["train"]),
    )
    assert setup.planner.resolve(context).stages[-1].arguments["context_splits"] == ["train"]
    context.inputs.context_splits = ["held_out"]
    with pytest.raises(TypeError, match="PredictionContext"):
        setup.planner.resolve(context)


@pytest.mark.skipif(sys.platform == "win32", reason="Submitit local executor requires Unix signals")
def test_stage_job_runs_through_real_submitit_local_executor(setup):
    import submitit

    from meds_algorithm.artifacts.manifest import digest_file

    plan = setup.planner.resolve(replace(setup.config, stages=["preprocess_data"]))
    plan.output_dir.mkdir()
    (plan.output_dir / "logs").mkdir()
    config = plan.output_dir / "algorithm.json"
    config.write_text(json.dumps(plan.algorithm_configuration))
    executor = submitit.LocalExecutor(folder=str(setup.repo.parent / "submitit-test"))
    executor.update_parameters(timeout_min=1)
    job = executor.submit(StageJob(plan.stages[0], plan.repo, plan.output_dir, digest_file(config)))
    assert job.result() == "preprocess_data"
    config.write_text("{}")
    with pytest.raises(ValueError, match="configuration changed"):
        StageJob(plan.stages[0], plan.repo, plan.output_dir, "old digest")()
