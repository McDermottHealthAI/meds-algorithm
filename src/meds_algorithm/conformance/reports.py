"""Completion evidence shared by generated repositories."""

import re


def _sections(text, level):
    parts = re.split(rf"^{'#' * level} (.+)\s*$", text, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def assert_implementation_report(report: str, profiles, stub_profiles) -> None:
    """Validate shared evidence and each completed profile, allowing unfinished profile sections."""
    assert set(stub_profiles) <= set(profiles), "Unknown profile in STUB_PROFILES"
    complete = set(profiles) - set(stub_profiles)
    if not complete:
        return
    sections = _sections(report, 2)
    required = {
        "Source",
        "Source-element ledger",
        "Inputs and predicates",
        "Intermediate artifacts",
        "Scientific deviations",
        "Verification",
        "Review gates",
        "Resource measurements",
        "Environment and provenance",
    }
    assert required <= sections.keys(), f"Missing report sections: {sorted(required - sections.keys())}"
    choices = _sections(sections.get("Profile choices", ""), 3)
    assert complete <= choices.keys(), f"Missing profile reports: {sorted(complete - choices.keys())}"
    inactive_sections = {
        section
        for section, profile in {
            "Zero-shot task translation": "zero_shot_direct",
            "Zero-shot materialization": "zero_shot_materialized",
        }.items()
        if profile not in complete
    }
    checked = {
        name: body
        for name, body in sections.items()
        if name != "Profile choices" and name not in inactive_sections
    }
    checked.update({f"Profile {profile}": choices[profile] for profile in complete})
    for name, body in checked.items():
        assert body.strip() and "TODO" not in body and "<paper/repository not yet supplied>" not in body, (
            f"Incomplete implementation report: {name}"
        )
