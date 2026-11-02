"""Resolve an auditable lifecycle without creating files or contacting a scheduler."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from omegaconf import OmegaConf

from meds_algorithm import STEP_SPECS, CommandName
from meds_algorithm.algorithms import request_type
from meds_algorithm.runtime.provenance import code_provenance

from .config import Resources, RunConfig


@dataclass(frozen=True)
class StagePlan:
    name: str
    arguments: dict[str, Any]
    argv: tuple[str, ...]
    depends_on: tuple[str, ...]
    resources: Resources


@dataclass(frozen=True)
class RunPlan:
    output_dir: Path
    repo: Path
    profile: str
    execution: str
    configuration: dict[str, Any]
    algorithm_configuration: dict[str, Any]
    provenance: dict[str, Any]
    stages: tuple[StagePlan, ...]

    def to_dict(self):
        result = asdict(self)
        result["output_dir"] = str(self.output_dir)
        result["repo"] = str(self.repo)
        return result


class RunPlanner:
    """Derive output types and artifact wiring from existing request specifications."""

    def __init__(self, repository, *, command: tuple[str, ...], base_dir: Path):
        self.repository = repository
        self.command = command
        self.base_dir = Path(base_dir).resolve()

    def _path(self, value):
        if not isinstance(value, str) or not value.strip() or value == "???":
            raise ValueError("Input and output paths must be nonempty strings")
        return (self.base_dir / value).resolve()

    def resolve(self, config: RunConfig) -> RunPlan:
        import json

        profile = self.repository.select_profile(config.profile)
        if config.execution not in {"local", "slurm"}:
            raise ValueError("execution must be local or slurm")
        order = tuple(self.repository.profile_commands(profile))
        selected = config.stages or list(order)
        if len(set(selected)) != len(selected) or set(selected) - set(order):
            raise ValueError("stages must be unique commands of the selected profile")
        if set(config.resources.steps) - set(order):
            raise ValueError("resources.steps contains an unknown profile command")
        output = self._path(config.output_dir)
        if output.exists():
            raise FileExistsError(f"Use a new output_dir: {output}")
        repo = self.repository.runner.repo
        if repo is None or not repo.is_dir():
            raise ValueError("Orchestration requires an explicit algorithm repository directory")
        algorithm_type = self.repository.implementations[profile].config_type
        algorithm = algorithm_type.from_dict(config.algorithm, base=self.base_dir)
        inputs = {
            key: str(self._path(value)) if value is not None else None
            for key, value in asdict(config.inputs).items()
            if key != "context_splits"
        }
        reused = {key: str(self._path(value)) for key, value in config.artifacts.items()}
        available = {}
        used = set()
        external_paths = set()
        plans = []
        for step in order:
            if step not in selected:
                continue
            spec = STEP_SPECS[CommandName(step)]
            destination = (
                output / "artifacts" / spec.output_argument.removeprefix("output_").removesuffix("_dir")
            )
            arguments = {spec.output_argument: str(destination), "seed": config.seed}
            for artifact in spec.artifact_inputs:
                if artifact.argument in reused:
                    if artifact.artifact_type in available:
                        raise ValueError(
                            f"Ambiguous {artifact.argument}: both reused and produced by this run"
                        )
                    arguments[artifact.argument] = reused[artifact.argument]
                    used.add(artifact.argument)
                    external_paths.add(Path(reused[artifact.argument]))
                elif artifact.artifact_type in available:
                    arguments[artifact.argument] = available[artifact.artifact_type]
                else:
                    raise ValueError(f"{step} requires artifacts.{artifact.argument} or its producer stage")
            for argument in spec.external_arguments:
                key = argument.removeprefix("external_")
                value = inputs.get(key)
                if step == "infer_embeddings" and key == "index_dir":
                    value = inputs["embedding_index_dir"] or value
                if value is None:
                    raise ValueError(f"{step} requires inputs.{key}")
                arguments[argument] = value
                external_paths.add(Path(value))
            if spec.requires_splits:
                arguments["splits"] = (
                    config.embedding_splits if step == "infer_embeddings" else config.prediction_splits
                )
            if step == "preprocess_data" and inputs["predicates_file"] is not None:
                arguments["external_predicates_file"] = inputs["predicates_file"]
            if spec.task_conditioned:
                predicates = inputs["task_predicates_file"] or inputs["predicates_file"]
                if predicates is not None:
                    arguments["external_predicates_file"] = predicates
            if step == "predict_only":
                if inputs["context_labels_dir"] is not None:
                    arguments["external_labels_dir"] = inputs["context_labels_dir"]
                    arguments["context_splits"] = config.inputs.context_splits
                elif config.inputs.context_splits:
                    raise ValueError("context_splits requires inputs.context_labels_dir")
                if inputs["task_criteria_file"] is not None:
                    arguments["external_task_criteria_file"] = inputs["task_criteria_file"]
                    predicates = inputs["task_predicates_file"] or inputs["predicates_file"]
                    if predicates is not None:
                        arguments["external_predicates_file"] = predicates
            request_cls = request_type(profile, step)
            request = request_cls.from_arguments(arguments)
            for argument, reference in request.artifact_inputs():
                if argument in reused:
                    reference.read_manifest()
            if "external_predicates_file" in arguments:
                external_paths.add(Path(arguments["external_predicates_file"]))
            if step == "preprocess_data" and algorithm.additional_predicates_file is not None:
                external_paths.add(algorithm.additional_predicates_file)
            if step == "predict_only" and inputs["context_labels_dir"] is not None:
                external_paths.add(Path(inputs["context_labels_dir"]))
            if spec.artifact_type.value == "predictions" and inputs["evaluation_labels_dir"] is not None:
                arguments["external_evaluation_labels_dir"] = inputs["evaluation_labels_dir"]
                external_paths.add(Path(inputs["evaluation_labels_dir"]))
            external_paths.update(
                Path(value) for key, value in arguments.items() if key.startswith("external_")
            )
            arguments["config_file"] = str(output / "algorithm.json")
            # Every stage has its own subprocess. The existing CLI remains the execution boundary.
            argv = (
                *self.command,
                str(step),
                "--profile",
                profile,
                *(f"{key}={json.dumps(value, allow_nan=False)}" for key, value in arguments.items()),
            )
            base = config.resources.cpu if step == "preprocess_data" else config.resources.compute
            resources = OmegaConf.to_object(
                OmegaConf.merge(OmegaConf.structured(base), config.resources.steps.get(step, {}))
            )
            resources.validate()
            plans.append(StagePlan(str(step), arguments, argv, (plans[-1].name,) if plans else (), resources))
            available[spec.artifact_type] = str(destination)
        if set(reused) != used:
            raise ValueError(f"Unused artifact overrides: {sorted(set(reused) - used)}")
        for path in external_paths:
            if not path.exists():
                raise FileNotFoundError(path)
            if path == output or path in output.parents or output in path.parents:
                raise ValueError(f"output_dir overlaps an input: {path}")
        # Report fully resolved paths/defaults, never an unresolved Hydra interpolation.
        resolved = asdict(config)
        resolved.update(
            output_dir=str(output),
            inputs={**inputs, "context_splits": config.inputs.context_splits},
            artifacts=reused,
            algorithm=algorithm.to_dict(),
        )
        return RunPlan(
            output,
            repo,
            profile,
            config.execution,
            resolved,
            {
                "schema_version": algorithm.schema_version,
                "type": f"{algorithm_type.__module__}.{algorithm_type.__qualname__}",
                "values": algorithm.to_dict(),
            },
            code_provenance(repo),
            tuple(plans),
        )
