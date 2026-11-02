"""Exercise inherited acceptance tests through real pytest collection and execution."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from meds_algorithm import ALGORITHM_PROFILES, AlgorithmConfig, NNConfig
from meds_algorithm.conformance.cases import AlgorithmCase
from meds_algorithm.conformance.suite import AlgorithmConformanceTests

pytest_plugins = ["pytester"]


def make_case(root, *, stubs=()):
    return AlgorithmCase(
        root=root,
        name="fixture_algorithm",
        create_repository=lambda: SimpleNamespace(
            profiles=tuple(ALGORITHM_PROFILES),
            profile_commands=lambda profile: ALGORITHM_PROFILES[profile],
        ),
        configurations=(AlgorithmConfig(), NNConfig(learning_rate=0.01, batch_size=4)),
        stub_profiles=set(stubs),
        run_e2e=lambda *args, **kwargs: pytest.fail("unexpected adapter execution"),
        fitted_codes=lambda artifacts: set(),
        prepare_meds_dev_run=lambda *args, **kwargs: pytest.fail("unexpected integration execution"),
    )


def test_case_requires_configs_and_registered_stubs(tmp_path):
    case = make_case(tmp_path)
    assert case.profiles == tuple(ALGORITHM_PROFILES)
    with pytest.raises(ValueError, match="representative"):
        replace(case, configurations=())
    with pytest.raises(ValueError, match="Unregistered stub"):
        replace(case, stub_profiles={"typo"})


@pytest.fixture
def downstream(pytester):
    # Import the helper from a stable copied module, not from pytest's test-module cache.
    helper = Path(__file__).read_text(encoding="utf-8").split("def test_case_requires")[0]
    pytester.makepyfile(case_helper=helper)
    pytester.makeconftest("""
import pytest
from meds_algorithm import ALGORITHM_PROFILES
from case_helper import make_case

@pytest.fixture(scope="session")
def algorithm_case(pytestconfig):
    return make_case(pytestconfig.rootpath, stubs=ALGORITHM_PROFILES)

@pytest.fixture(scope="session", params=list(ALGORITHM_PROFILES))
def profile(request):
    return request.param
""")
    pytester.makepyfile(
        test_acceptance="""
from meds_algorithm.conformance.suite import AlgorithmConformanceTests
class TestConformance(AlgorithmConformanceTests):
    pass
"""
    )
    pytester.makeini("""
[pytest]
markers =
    slow: integration
    meds_dev: opt-in integration
    real_data: opt-in data
""")
    return pytester


def test_inherited_suite_collects_every_profile_without_duplicate_base(downstream):
    result = downstream.runpytest_subprocess("--collect-only", "-q", "--strict-markers")
    result.assert_outcomes()  # collection succeeds without executing adapters
    output = result.stdout.str()
    assert "38 tests collected" in output
    for profile in ALGORITHM_PROFILES:
        for test in (
            "test_end_to_end",
            "test_meds_dev_runs_algorithm_yaml",
            "test_full_dag_on_mimic_iv_demo",
        ):
            assert f"TestConformance::{test}[{profile}]" in output
    assert "::AlgorithmConformanceTests::" not in output


def test_stubs_skip_execution_but_contract_and_configs_still_run(downstream):
    result = downstream.runpytest_subprocess(
        "-q", "-k", "end_to_end or profile_implementations or configuration_roundtrips"
    )
    result.assert_outcomes(passed=7, skipped=6, deselected=25)


@pytest.mark.parametrize("selection", [[], ["-m", "not slow"], ["-m", "slow"]])
def test_completed_integrations_need_explicit_opt_in(downstream, selection):
    conftest = downstream.path / "conftest.py"
    conftest.write_text(conftest.read_text().replace("stubs=ALGORITHM_PROFILES", "stubs=()"))
    result = downstream.runpytest_subprocess("-q", "-k", "meds_dev_runs or full_dag", *selection)
    if selection == ["-m", "not slow"]:
        result.assert_outcomes(deselected=38)
    else:
        result.assert_outcomes(skipped=12, deselected=26)


def test_integration_markers_select_only_their_suite(downstream):
    for marker, expected, excluded in (
        ("meds_dev", "test_meds_dev_runs_algorithm_yaml", "test_full_dag_on_mimic_iv_demo"),
        ("real_data", "test_full_dag_on_mimic_iv_demo", "test_meds_dev_runs_algorithm_yaml"),
    ):
        result = downstream.runpytest_subprocess("--collect-only", "-q", "-m", marker)
        assert expected in result.stdout.str()
        assert excluded not in result.stdout.str()
        assert "6/38 tests collected" in result.stdout.str()


def test_mixed_completion_does_not_hide_report_requirements(tmp_path):
    (tmp_path / "IMPLEMENTATION_REPORT.md").write_text("# Unfinished\n")
    case = make_case(tmp_path, stubs=ALGORITHM_PROFILES)
    suite = AlgorithmConformanceTests()
    suite.test_completed_algorithm_has_a_completed_report(case)
    case.stub_profiles.remove("supervised")
    with pytest.raises(AssertionError, match="Missing report sections"):
        suite.test_completed_algorithm_has_a_completed_report(case)


@pytest.mark.parametrize("completed", [{"supervised"}, {"probe", "zero_shot_direct"}])
def test_provisioning_requires_task_capability_only_for_completed_zero_shot(tmp_path, monkeypatch, completed):
    from meds_algorithm.conformance import suite

    case = make_case(tmp_path, stubs=set(ALGORITHM_PROFILES) - completed)
    calls = []
    monkeypatch.setattr(
        suite.integration,
        "provision_meds_dev",
        lambda *args, **kwargs: calls.append(kwargs) or tmp_path,
    )
    result = AlgorithmConformanceTests.meds_dev.__wrapped__(
        AlgorithmConformanceTests(), object(), object(), case
    )
    assert result == tmp_path
    assert calls == [{"task_criteria": any(p.startswith("zero_shot_") for p in completed)}]
