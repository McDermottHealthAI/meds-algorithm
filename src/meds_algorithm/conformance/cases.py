"""Algorithm-owned inputs to the shared acceptance suite; no pytest dependency."""

from collections.abc import Callable, Mapping, Sequence, Set
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from meds_algorithm.configuration import AlgorithmConfig
from meds_algorithm.runner import AlgorithmRepository

from .types import E2EResult, MEDSDevRun


class ProfileRunner(Protocol):
    """Run a real lifecycle with fresh outputs, honoring conformance input overrides."""

    def __call__(self, directory: Path, /, *, profile: str, **inputs: Any) -> E2EResult: ...


class MEDSDevPreparer(Protocol):
    """Prepare the algorithm-specific arguments and expected evaluation index."""

    def __call__(self, meds_dev: Path, directory: Path, /, *, profile: str) -> MEDSDevRun: ...


@dataclass(frozen=True, kw_only=True)
class AlgorithmCase:
    """Explicit connection between a repository and reusable acceptance tests.

    Supply representative concrete configs, including required constructor arguments.
    Adapter functions remain algorithm-owned; they must execute real implementations.
    Profiles are derived from the repository instead of declared a second time here.
    """

    root: Path
    name: str
    create_repository: Callable[[], AlgorithmRepository]
    configurations: Sequence[AlgorithmConfig]
    stub_profiles: Set[str]
    run_e2e: ProfileRunner
    fitted_codes: Callable[[Mapping[str, Path]], Set[str]]
    prepare_meds_dev_run: MEDSDevPreparer

    def __post_init__(self):
        if not self.configurations:
            raise ValueError("Supply at least one representative algorithm configuration")
        if not self.profiles:
            raise ValueError("The repository must register at least one profile")
        unknown = set(self.stub_profiles) - set(self.profiles)
        if unknown:
            raise ValueError(f"Unregistered stub profiles: {sorted(unknown)}")

    @property
    def profiles(self) -> tuple[str, ...]:
        return self.create_repository().profiles
