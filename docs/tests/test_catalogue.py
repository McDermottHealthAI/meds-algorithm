"""Catalogue evidence is curated; network observations cannot silently promote it."""

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("catalogue", ROOT / "docs/catalogue.py")
catalogue = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(catalogue)


def sample_entry():
    return copy.deepcopy(catalogue.load_catalogue(ROOT / "catalogue/algorithms.yaml")[0])


def write_registry(tmp_path, entries):
    path = tmp_path / "algorithms.yaml"
    path.write_text(yaml.safe_dump({"schema_version": 1, "algorithms": entries}), encoding="utf-8")
    return path


def test_private_unpublished_entry_renders_without_network(monkeypatch):
    monkeypatch.setattr(catalogue, "fetch_json", lambda url: pytest.fail("Docs must build offline"))
    page = SimpleNamespace(file=SimpleNamespace(src_uri="implemented-algorithms.md"))
    result = catalogue.on_page_markdown("<!-- algorithm-catalogue -->", page)
    assert "genhpf-meds" in result
    assert "Private — access required" in result
    assert "Implementation under review" in result
    assert "Pass reported" in result and "Pending" in result
    assert "python -m pip install" not in result
    assert "f749d61fbbec92b1cd05d57fdeaa428c365cc266/IMPLEMENTATION_REPORT.md" in result


def test_published_entry_generates_escaped_pinned_install_command(tmp_path):
    entry = sample_entry()
    entry["package"]["pypi_version"] = "0.2.0a1"
    entry["name"] = '<script>alert("name")</script>'
    entry["notes"] = '<img src=x onerror="alert(1)">'
    entries = catalogue.load_catalogue(write_registry(tmp_path, [entry]))
    result = catalogue.render_catalogue(entries)
    assert 'python -m pip install "genhpf-meds==0.2.0a1"' in result
    assert "https://pypi.org/project/genhpf-meds/0.2.0a1/" in result
    assert "<script>" not in result and "<img " not in result


@pytest.mark.parametrize(
    "field,value",
    [
        ("revision", "main"),
        ("profiles", ["unknown"]),
        ("profiles", ["supervised", "supervised"]),
        ("public_listing", False),
        ("access", "secret"),
        ("implementation_status", "validated"),
        ("implementation_pr", None),
        ("reviewed_on", "2099-01-01"),
        ("repository", "https://example.com/user/repo"),
        ("paper", "javascript:alert(1)"),
    ],
)
def test_registry_rejects_ambiguous_or_unsafe_entries(tmp_path, field, value):
    entry = sample_entry()
    entry[field] = value
    with pytest.raises(ValueError):
        catalogue.load_catalogue(write_registry(tmp_path, [entry]))


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("package", "name", "name;echo bad"),
        ("package", "pypi_version", '1.0";echo bad'),
        ("evidence", "report", "../secret.md"),
        ("evidence", "synthetic", "maybe"),
    ],
)
def test_registry_rejects_invalid_install_or_evidence_fields(tmp_path, section, field, value):
    entry = sample_entry()
    entry[section][field] = value
    with pytest.raises(ValueError):
        catalogue.load_catalogue(write_registry(tmp_path, [entry]))


def test_registry_rejects_duplicates_and_unknown_fields(tmp_path):
    entry = sample_entry()
    with pytest.raises(ValueError, match="unique"):
        catalogue.load_catalogue(write_registry(tmp_path, [entry, entry]))
    entry["unknown_field"] = True
    with pytest.raises(ValueError, match="expected fields"):
        catalogue.load_catalogue(write_registry(tmp_path, [entry]))


def test_release_observer_skips_private_source_and_never_changes_evidence():
    entry = sample_entry()
    before = copy.deepcopy(entry)
    calls = []

    def fetch(url):
        calls.append(url)
        assert url == "https://pypi.org/pypi/genhpf-meds/json"
        return {
            "releases": {
                "0.1.0": [{"yanked": False}],
                "0.2.0a1": [{"yanked": False}],
                "9.0.0": [{"yanked": True}],
                "10.0.0": [],
                "bad": [{}],
            }
        }

    first = catalogue.observe_releases([entry], fetch)
    second = catalogue.observe_releases([entry], fetch)
    assert first == second  # No timestamp-only changes or update-PR churn.
    result = first["observations"][entry["id"]]
    assert result["repository"] == "private_manual_review"
    assert result["latest_pypi_release"] == "0.2.0a1"
    assert result["reviewed_pypi_release"] is None
    assert entry == before
    assert len(calls) == 2


def test_missing_public_repository_and_yanked_reviewed_release_are_observed():
    entry = sample_entry()
    entry["access"] = "public"
    entry["package"]["pypi_version"] = "0.1.0"

    def fetch(url):
        if "api.github.com" in url:
            return None
        return {"releases": {"0.1.0": [{"yanked": True}]}}

    result = catalogue.observe_releases([entry], fetch)["observations"][entry["id"]]
    assert result["repository"] == "unavailable_or_private"
    assert result["reviewed_release_available"] is False


def test_public_github_release_and_absent_pypi_are_observed():
    entry = sample_entry()
    entry["access"] = "public"

    def fetch(url):
        if url.endswith("/releases/latest"):
            return {"tag_name": "v0.3.0"}
        return {} if "pypi.org" in url else {"name": "algorithm"}

    result = catalogue.observe_releases([entry], fetch)["observations"][entry["id"]]
    assert result["latest_github_release"] == "v0.3.0"
    assert result["pypi"] == "not_found"


@pytest.mark.parametrize("code", [403, 429, 500])
def test_network_errors_are_not_missing_release_evidence(monkeypatch, code):
    def fail(request, **kwargs):
        assert "Authorization" not in request.headers
        raise HTTPError(request.full_url, code, "temporary error", None, None)

    monkeypatch.setattr(catalogue, "urlopen", fail)
    with pytest.raises(HTTPError):
        catalogue.fetch_json("https://pypi.org/pypi/example/json")


def test_observation_snapshot_contains_only_metadata():
    data = json.loads((ROOT / "catalogue/updates.json").read_text())
    assert data["schema_version"] == 1
    assert set(data["observations"]) == {
        entry["id"] for entry in catalogue.load_catalogue(ROOT / "catalogue/algorithms.yaml")
    }
