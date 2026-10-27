"""The single public execution path for typed algorithms and their CLI adapters."""

from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from pathlib import Path

from .algorithms import Algorithm, profile_class, request_type
from .artifacts.manifest import digest_config, digest_file, measured_artifact
from .artifacts.references import ArtifactDestination, PayloadMetadata, PredictionsArtifact
from .requests import PredictionContext, PredictionIndex, StepRequest
from .tasks.spec import RelaxationLedger


def _paths(value):
    if isinstance(value, Path):
        yield value
    elif is_dataclass(value):
        for field in fields(value):
            yield from _paths(getattr(value, field.name))


class StepRunner:
    """A fresh algorithm instance is supplied per call; persisted artifacts carry fitted state."""

    def __init__(self, *, repo: Path | None = None):
        self.repo = None if repo is None else Path(repo).resolve()

    def run(
        self,
        algorithm: Algorithm,
        step: str,
        request: StepRequest,
        *,
        profile: str,
        evaluation_labels_dir: Path | None = None,
    ):
        expected = request_type(profile, step)
        if not isinstance(algorithm, profile_class(profile)):
            raise TypeError(f"Algorithm does not implement {profile}")
        if type(request) is not expected:
            raise TypeError(f"{step} requires {expected.__name__}")
        # Reconstruct to enforce types/value invariants even for hand-built Python requests.
        request = expected.from_dict(request.to_dict())
        algorithm.config_type.from_dict(algorithm.config.to_dict())
        destination = request.output.directory
        input_paths = [
            path
            for field in fields(request)
            if field.name != "output"
            for path in _paths(getattr(request, field.name))
        ]
        if evaluation_labels_dir is not None:
            if request.result_type is not PredictionsArtifact:
                raise ValueError("Evaluation labels are allowed only after prediction")
            evaluation_labels_dir = Path(evaluation_labels_dir).resolve()
            input_paths.append(evaluation_labels_dir)
        for path in input_paths:
            if not path.exists():
                raise FileNotFoundError(path)
            if destination == path or destination in path.parents or path in destination.parents:
                raise ValueError("Output must not overlap any input path")
        inputs = {}
        for argument, artifact in request.artifact_inputs():
            artifact.read_manifest()
            inputs[argument] = {
                "path": str(artifact.directory),
                "manifest_digest": digest_file(artifact.directory / "manifest.yaml"),
            }
        index = getattr(request, "index", None)
        if isinstance(index, PredictionIndex):
            keys = index.read()
            inputs["external_index_dir"] = {
                "path": str(index.directory),
                "splits": list(index.splits),
                "keys_digest": digest_config(keys.sort(["subject_id", "prediction_time"]).write_json()),
            }
        context = getattr(request, "context", None)
        if isinstance(context, PredictionContext):
            context.read(index)  # Disjoint keys and permitted split names, before model code.
        task = getattr(request, "task", None)
        if task is not None:
            if task.predicates_file != request.predicates_file:
                raise ValueError("Task predicates and request predicates must agree")
            inputs["task"] = task.provenance()
        algorithm.validate_inputs(request)
        metadata = None
        details = {
            "algorithm": {
                "name": algorithm.name,
                "implementation": f"{type(algorithm).__module__}.{type(algorithm).__qualname__}",
                "config_type": f"{type(algorithm.config).__module__}.{type(algorithm.config).__qualname__}",
                "config_schema_version": algorithm.config.schema_version,
                "config": algorithm.config.to_dict(),
            },
            "invocation": {
                "profile": profile,
                "request": request.to_dict(),
                "evaluation_labels_dir": None
                if evaluation_labels_dir is None
                else str(evaluation_labels_dir),
            },
        }
        with measured_artifact(
            destination,
            artifact_type=request.result_type.kind.value,
            command=step,
            producer=f"{type(algorithm).__module__}.{type(algorithm).__qualname__}.{step}",
            payload_format=lambda: f"{metadata.format}/v{metadata.version}",
            inputs=inputs,
            config_digest=digest_config({"config": algorithm.config.to_dict(), "request": request.to_dict()}),
            semantics_digest=None if task is None else task.semantics_digest(),
            external_predicates_file=request.predicates_file,
            overwrite=request.execution.overwrite,
            repo=self.repo,
            manifest_fields=details,
        ) as staging:
            working = replace(request, output=ArtifactDestination(staging))
            metadata = getattr(algorithm, step)(working)
            if algorithm.config.to_dict() != details["algorithm"]["config"]:
                raise ValueError("Algorithm configuration changed during execution")
            if not isinstance(metadata, PayloadMetadata):
                raise TypeError("Algorithm methods must return PayloadMetadata")
            if (staging / "manifest.yaml").exists():
                raise ValueError("Only the runner may write manifest.yaml")
            if request.result_type is PredictionsArtifact:
                self._validate_predictions(staging, index, evaluation_labels_dir)
                if profile.startswith("zero_shot_"):
                    RelaxationLedger.read(staging)
            for reserved in ("config.json", "request.json"):
                if (staging / reserved).exists():
                    raise ValueError(f"{reserved} is reserved for runner provenance")
            algorithm.config.save(staging / "config.json")
            request.save(staging / "request.json")
        return request.result_type.open(destination)

    @staticmethod
    def _validate_predictions(staging, index, evaluation_labels_dir):
        import polars as pl

        from .evaluation.predictions import attach_ground_truth, check_decoded

        paths = sorted(staging.rglob("*.parquet"))
        if not paths:
            raise ValueError("Predictions must contain Parquet shards")
        frames = [pl.read_parquet(path) for path in paths]
        if any("boolean_value" in frame.columns for frame in frames):
            raise ValueError(
                "Model predictions must not contain ground truth; runner attaches it after scoring"
            )
        check_decoded(index.read(), pl.concat(frames))
        if evaluation_labels_dir is not None:
            for path, frame in zip(paths, frames, strict=True):
                attach_ground_truth(frame, evaluation_labels_dir, index.splits).write_parquet(path)


class AlgorithmRepository:
    """Only a profile-to-implementation association; signatures and order live on the ABCs."""

    def __init__(self, implementations: dict[str, type[Algorithm]], *, repo: Path | None = None):
        if not implementations:
            raise ValueError("At least one profile implementation is required")
        for profile, implementation in implementations.items():
            if not isinstance(implementation, type) or not issubclass(implementation, profile_class(profile)):
                raise TypeError(f"Implementation must inherit {profile_class(profile).__name__}")
            if implementation.__abstractmethods__:
                raise TypeError(
                    f"Unimplemented abstract methods: {sorted(implementation.__abstractmethods__)}"
                )
        self.implementations = dict(implementations)
        self.profiles = tuple(implementations)
        self.runner = StepRunner(repo=repo)

    def select_profile(self, profile=None):
        if profile is None:
            if len(self.profiles) != 1:
                raise ValueError("Several profiles are declared; select one with --profile")
            return self.profiles[0]
        if profile not in self.implementations:
            raise ValueError(f"Profile {profile!r} is not declared")
        return profile

    def profile_commands(self, profile=None):
        return profile_class(self.select_profile(profile)).steps

    def run(self, step: str, arguments: dict, *, profile=None):
        profile = self.select_profile(profile)
        request_cls = request_type(profile, step)
        arguments = dict(arguments)
        implementation = self.implementations[profile]
        config_file = arguments.pop("config_file", None)
        config = (
            implementation.config_type.from_file(config_file) if config_file else implementation.config_type()
        )
        evaluation = arguments.pop("external_evaluation_labels_dir", None)
        return self.runner.run(
            implementation(config),
            step,
            request_cls.from_arguments(arguments),
            profile=profile,
            evaluation_labels_dir=evaluation,
        )
