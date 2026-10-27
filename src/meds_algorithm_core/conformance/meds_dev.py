"""Shared opt-in integration-test utilities."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from ..runtime.process import run
from .assertions import assert_prediction_keys as assert_prediction_keys
from .assertions import assert_prediction_schema as assert_prediction_schema

MEDS_DEV_URL = "https://github.com/Medical-Event-Data-Standard/MEDS-DEV.git"
# Head of MEDS-DEV PR #330 (task_criteria_path), on top of dev, which contains PR #325 (predicates_path).
# Repin to the merge commit once #330 merges: a branch commit can become unreachable after a squash merge.
MEDS_DEV_PINNED_REF = "19a8aa3417fae3586b2e8f0f17aba19ddb0560d4"
INSTALL_TIMEOUT = 1800
RUN_TIMEOUT = 5400


def venv_bin(checkout: Path) -> Path:
    return checkout / ".venv" / ("Scripts" if sys.platform == "win32" else "bin")


def assert_meds_dev_predicates_capability(checkout: Path) -> None:
    """Require the explicit predicates_path passthrough proposed in MEDS-DEV PR #325."""
    config = checkout / "src" / "MEDS_DEV" / "configs" / "_run_model.yaml"
    implementation = checkout / "src" / "MEDS_DEV" / "models" / "__init__.py"
    if not config.is_file() or not implementation.is_file():
        raise AssertionError(f"{checkout} is not a MEDS-DEV source checkout")
    if (
        "predicates_path:" not in config.read_text()
        or 'format_kwargs["predicates_path"]' not in implementation.read_text()
    ):
        raise AssertionError(
            "MEDS-DEV lacks the predicates_path algorithm-command passthrough. Use MEDS_DEV_REF="
            f"{MEDS_DEV_PINNED_REF} or a revision containing MEDS-DEV PR #325."
        )


def assert_meds_dev_task_criteria_capability(checkout: Path) -> None:
    """Require the task_criteria_path passthrough proposed in MEDS-DEV PR #330 (zero-shot profiles)."""
    implementation = checkout / "src" / "MEDS_DEV" / "models" / "__init__.py"
    if 'format_kwargs["task_criteria_path"]' not in implementation.read_text():
        raise AssertionError(
            "MEDS-DEV lacks the task_criteria_path algorithm-command passthrough that zero-shot model.yaml "
            f"commands use. Use MEDS_DEV_REF={MEDS_DEV_PINNED_REF} or a revision containing MEDS-DEV PR #330."
        )


def provision_meds_dev(request, tmp_path_factory, *, task_criteria: bool = False) -> Path:
    source = os.environ.get("MEDS_DEV_DIR")
    expression = request.config.getoption("markexpr", default="") or ""
    from _pytest.mark.expression import Expression

    selected = False
    if expression.strip():
        marker_expression = Expression.compile(expression)
        selected = not marker_expression.evaluate(lambda name, **kwargs: name == "slow") and any(
            marker_expression.evaluate(lambda name, marker=marker, **kwargs: name in {marker, "slow"})
            for marker in ("meds_dev", "real_data")
        )
    if not selected:
        pytest.skip("explicitly select -m meds_dev or -m real_data; MEDS_DEV_DIR alone does not opt in")
    uv = shutil.which("uv")
    git = shutil.which("git")
    if uv is None or git is None:
        pytest.skip("uv and git are required for MEDS-DEV integration")
    checkout = tmp_path_factory.mktemp("meds-dev") / "MEDS-DEV"
    run([git, "clone", source or MEDS_DEV_URL, checkout], timeout=INSTALL_TIMEOUT)
    if source is None:
        ref = os.environ.get("MEDS_DEV_REF", MEDS_DEV_PINNED_REF)
        run([git, "-C", checkout, "checkout", "--detach", ref], timeout=INSTALL_TIMEOUT)
    assert_meds_dev_predicates_capability(checkout)
    if task_criteria:
        assert_meds_dev_task_criteria_capability(checkout)
    run([uv, "venv", checkout / ".venv"], timeout=INSTALL_TIMEOUT)
    run(
        [uv, "pip", "install", "-e", checkout, "--python", venv_bin(checkout) / "python"],
        timeout=INSTALL_TIMEOUT,
        env={"SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MEDS_DEV": "0.0.0"},
    )
    return checkout


def prepare_mimic_demo(meds_dev, tmp_path):
    """Return MEDS-DEV's ``(MIMIC demo, task labels, MIMIC predicates)`` paths.

    Use ``MEDS_DEMO_DIR`` when set; otherwise invoke MEDS-DEV's own demo builder. Pin an existing
    demo-compatible MEDS-DEV task rather than defining a task in this repository.
    """
    configured = os.environ.get("MEDS_DEMO_DIR")
    dataset_dir = Path(configured).resolve() if configured else tmp_path / "mimic-iv-demo"
    if not configured:
        run(
            [
                venv_bin(meds_dev) / "meds-dev-dataset",
                "dataset=MIMIC-IV",
                f"output_dir={dataset_dir}",
                "demo=true",
            ],
            timeout=RUN_TIMEOUT,
        )
    labels_dir = tmp_path / "mortality-in-icu-first-24h"
    run(
        [
            venv_bin(meds_dev) / "meds-dev-task",
            "task=mortality/in_icu/first_24h",
            "dataset=MIMIC-IV",
            f"dataset_dir={dataset_dir}",
            f"output_dir={labels_dir}",
        ],
        # MEDS-DEV's task runner launches venv-installed helpers by bare name.
        # Prepend the pinned checkout so an ambient MEDS-DEV install cannot win.
        env={"PATH": f"{venv_bin(meds_dev)}{os.pathsep}{os.environ['PATH']}"},
        timeout=RUN_TIMEOUT,
    )
    predicates_file = meds_dev / "src" / "MEDS_DEV" / "datasets" / "MIMIC-IV" / "predicates.yaml"
    return dataset_dir, labels_dir, predicates_file


def mimic_task_criteria(meds_dev) -> Path:
    """MEDS-DEV's own ACES criteria for the demo task: what a zero-shot algorithm is asked to predict."""
    return meds_dev / "src" / "MEDS_DEV" / "tasks" / "mortality" / "in_icu" / "first_24h.yaml"
