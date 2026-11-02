"""Execute a resolved plan locally or submit each stage with an afterok dependency."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from meds_algorithm.artifacts.manifest import digest_file
from meds_algorithm.runtime.process import run
from meds_algorithm.runtime.provenance import code_provenance

from .planning import RunPlan, StagePlan


@dataclass(frozen=True)
class StageJob:
    """Small serializable callable; never pickle a fitted algorithm or GPU state."""

    stage: StagePlan
    repo: Path
    output_dir: Path
    config_digest: str
    expected_commit: str | None = None

    def __call__(self):
        if digest_file(self.output_dir / "algorithm.json") != self.config_digest:
            raise ValueError("Resolved algorithm configuration changed after planning")
        if self.expected_commit is not None:
            provenance = code_provenance(self.repo)
            if provenance["git_commit"] != self.expected_commit or provenance["dirty"] is not False:
                raise ValueError("Algorithm checkout changed after SLURM submission")
        run(
            self.stage.argv,
            cwd=self.repo,
            timeout=self.stage.resources.timeout_min * 60,
            log_path=self.output_dir / "logs" / f"{self.stage.name}.log",
        )
        return self.stage.name


class LocalExecution:
    def execute(self, plan: RunPlan, config_digest: str):
        for stage in plan.stages:
            StageJob(stage, plan.repo, plan.output_dir, config_digest)()


class SubmititExecution:
    """One scheduler job per stage; return after submission, not after training."""

    def execute(self, plan: RunPlan, config_digest: str):
        import submitit

        jobs = []
        receipt = {"status": "submitting", "jobs": []}

        def save():
            temporary = plan.output_dir / "submission.tmp"
            temporary.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
            temporary.replace(plan.output_dir / "submission.json")

        save()
        try:
            for stage in plan.stages:
                executor = submitit.AutoExecutor(
                    folder=str(plan.output_dir / "submitit" / stage.name / "%j"), cluster="slurm"
                )
                resources = stage.resources
                parameters = {
                    "timeout_min": resources.timeout_min,
                    "cpus_per_task": resources.cpus_per_task,
                    "mem_gb": resources.mem_gb,
                    "gpus_per_node": resources.gpus_per_node,
                    "nodes": 1,
                    "tasks_per_node": 1,
                    "name": f"{plan.profile}-{stage.name}",
                    **{
                        f"slurm_{key}": value
                        for key in ("partition", "account", "qos")
                        if (value := getattr(resources, key)) is not None
                    },
                }
                if jobs:
                    parameters["slurm_additional_parameters"] = {"dependency": f"afterok:{jobs[-1].job_id}"}
                executor.update_parameters(**parameters)
                job = executor.submit(
                    StageJob(stage, plan.repo, plan.output_dir, config_digest, plan.provenance["git_commit"])
                )
                jobs.append(job)
                receipt["jobs"].append({"stage": stage.name, "job_id": job.job_id})
                save()
            receipt["status"] = "submitted"
            save()
        except BaseException:
            receipt["status"] = "submission_failed"
            receipt["cancellation_errors"] = []
            for job in jobs:
                try:
                    job.cancel()
                except Exception as error:
                    receipt["cancellation_errors"].append({"job_id": job.job_id, "error": str(error)})
            save()
            raise


class RunCoordinator:
    """Persist one resolved plan, then choose the execution backend."""

    def execute(self, plan: RunPlan):
        if plan.execution == "slurm":
            # Refuse unknown or dirty code before creating files or submitting anything.
            current = code_provenance(plan.repo)
            if not current["git_commit"] or current["dirty"] is not False or current != plan.provenance:
                raise ValueError("SLURM requires an unchanged, clean committed algorithm checkout")
            if plan.output_dir.is_relative_to(plan.repo):
                ignored = subprocess.run(
                    ["git", "-C", str(plan.repo), "check-ignore", "--quiet", str(plan.output_dir)],
                    check=False,
                )
                if ignored.returncode != 0:
                    raise ValueError("SLURM output_dir must be outside the checkout or Git-ignored")
            import submitit  # noqa: F401 -- validate optional dependency before creating the run
        plan.output_dir.mkdir(parents=True, exist_ok=False)
        (plan.output_dir / "logs").mkdir()
        (plan.output_dir / "plan.json").write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
        config = plan.output_dir / "algorithm.json"
        config.write_text(json.dumps(plan.algorithm_configuration, indent=2), encoding="utf-8")
        backend = LocalExecution() if plan.execution == "local" else SubmititExecution()
        backend.execute(plan, digest_file(config))
