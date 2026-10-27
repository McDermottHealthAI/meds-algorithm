import pytest

from meds_algorithm_core.conformance.reports import assert_implementation_report


def report():
    shared = [
        "Source",
        "Source-element ledger",
        "Inputs and predicates",
        "Intermediate artifacts",
        "Scientific deviations",
        "Verification",
        "Review gates",
        "Resource measurements",
        "Environment and provenance",
    ]
    return (
        "\n".join(f"## {title}\nRecorded evidence.\n" for title in shared)
        + "\n## Profile choices\n### supervised\nCompleted evidence.\n### probe\nTODO\n"
    )


def test_unfinished_profile_does_not_hide_completed_evidence():
    assert_implementation_report(report(), ["supervised", "probe"], {"probe"})
    for broken in (
        report().replace("Completed evidence.", "TODO"),
        report().replace("Recorded evidence.", "TODO", 1),
        report().replace("### supervised", "### missing"),
    ):
        with pytest.raises(AssertionError):
            assert_implementation_report(broken, ["supervised", "probe"], {"probe"})


def test_completing_last_profile_requires_its_evidence():
    with pytest.raises(AssertionError, match="Profile probe"):
        assert_implementation_report(report(), ["supervised", "probe"], set())
    assert_implementation_report(report().replace("TODO", "Complete."), ["supervised", "probe"], set())
