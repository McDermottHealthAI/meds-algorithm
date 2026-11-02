"""Hydra composition without launcher side effects; the coordinator owns execution."""

import argparse
import json
import sys
from pathlib import Path

from hydra import compose, initialize_config_dir
from hydra.core.config_store import ConfigStore
from omegaconf import OmegaConf

from .config import RunConfig
from .execution import RunCoordinator
from .planning import RunPlanner


def compose_run(config_dir: Path, config_name: str, overrides: list[str]) -> RunConfig:
    # This schema is shared by every generated repository. Hydra owns the registry.
    ConfigStore.instance().store(name="meds_run", node=RunConfig)
    with initialize_config_dir(version_base="1.3", config_dir=str(config_dir.resolve())):
        config = compose(config_name=config_name, overrides=overrides)
        config = OmegaConf.merge(OmegaConf.structured(RunConfig), config)
        OmegaConf.to_container(config, resolve=True, throw_on_missing=True)
        return OmegaConf.to_object(config)


def main(repository, *, module: str, argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Prototype: plan/run a profile with Hydra configuration")
    parser.add_argument("--config-dir", type=Path, default=Path.cwd() / "configs" / "runs")
    parser.add_argument("--config-name", default="run")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the resolved plan without writing/submitting"
    )
    parser.add_argument("overrides", nargs="*", help="Hydra overrides, e.g. execution=slurm")
    args = parser.parse_args(argv)
    config = compose_run(args.config_dir, args.config_name, args.overrides)
    plan = RunPlanner(repository, command=(sys.executable, "-m", module), base_dir=Path.cwd()).resolve(config)
    if args.dry_run:
        print(json.dumps(plan.to_dict(), indent=2))
    else:
        RunCoordinator().execute(plan)
        print(f"{'Submitted' if plan.execution == 'slurm' else 'Completed'}: {plan.output_dir}")
