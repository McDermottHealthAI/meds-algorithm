"""Validate/render the curated catalogue offline; optionally observe public release metadata."""

import argparse
import json
import re
from datetime import date
from html import escape
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

import yaml
from packaging.version import InvalidVersion, Version

from meds_algorithm import ALGORITHM_PROFILES

ROOT = Path(__file__).resolve().parents[1]
VALIDATION_LABELS = {
    "reported_pass": "Pass reported",
    "pending": "Pending",
    "not_run": "Not run",
    "failed": "Failed",
    "not_reported": "Not reported",
}
STATUS_LABELS = {
    "implemented": "Implemented",
    "in_review": "Implementation under review",
    "in_progress": "Implementation in progress",
}


def exact_fields(value, fields, context):
    if not isinstance(value, dict) or set(value) != set(fields.split()):
        raise ValueError(f"{context}: expected fields {fields}")


def text(value, context):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}: expected nonempty text")
    return value


def https_url(value):
    parts = urlsplit(text(value, "URL"))
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("URLs must use HTTPS without credentials")
    return value


def release_version(value):
    # Also restrict characters before a version is used in a generated shell command.
    if not isinstance(value, str) or not re.fullmatch(r"[0-9A-Za-z.!+_-]+", value):
        raise ValueError("Invalid package version")
    try:
        return Version(value)
    except InvalidVersion as error:
        raise ValueError("Invalid package version") from error


def load_catalogue(path):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    exact_fields(data, "schema_version algorithms", "catalogue")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported catalogue schema")
    if not isinstance(data["algorithms"], list):
        raise ValueError("algorithms must be a list")
    identifiers = set()
    repositories = set()
    for entry in data["algorithms"]:
        exact_fields(
            entry,
            "id name description repository access public_listing paper profiles "
            "implementation_status implementation_pr revision reviewed_on package evidence notes",
            "entry",
        )
        identifier = text(entry["id"], "id")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", identifier) or identifier in identifiers:
            raise ValueError("Catalogue ids must be unique lowercase slugs")
        identifiers.add(identifier)
        for field in ("name", "description", "notes"):
            text(entry[field], field)
        repository = text(entry["repository"], "repository")
        if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Expected canonical GitHub repository URL")
        if repository.lower() in repositories:
            raise ValueError("Duplicate repository")
        repositories.add(repository.lower())
        if entry["access"] not in ("public", "private") or entry["public_listing"] is not True:
            raise ValueError(
                "Every listing needs explicit public metadata approval and an access designation"
            )
        if entry["paper"] is not None:
            https_url(entry["paper"])
        profiles = entry["profiles"]
        if (
            not isinstance(profiles, list)
            or not profiles
            or not all(isinstance(p, str) for p in profiles)
            or len(set(profiles)) != len(profiles)
            or not set(profiles) <= set(ALGORITHM_PROFILES)
        ):
            raise ValueError("Unknown, empty or duplicate profiles")
        if entry["implementation_status"] not in STATUS_LABELS:
            raise ValueError("Unknown implementation status")
        pr = entry["implementation_pr"]
        if pr is not None and (type(pr) is not int or pr <= 0):
            raise ValueError("implementation_pr must be null or a positive integer")
        if entry["implementation_status"] == "in_review" and pr is None:
            raise ValueError("An implementation under review needs its PR number")
        if not isinstance(entry["revision"], str) or not re.fullmatch(r"[0-9a-f]{40}", entry["revision"]):
            raise ValueError("Review must pin a full immutable commit SHA")
        reviewed = date.fromisoformat(text(entry["reviewed_on"], "reviewed_on"))
        if reviewed > date.today():
            raise ValueError("Review date cannot be in the future")
        exact_fields(entry["package"], "name pypi_version", "package")
        package = entry["package"]
        if not isinstance(package["name"], str) or not re.fullmatch(
            r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?", package["name"]
        ):
            raise ValueError("Invalid distribution name")
        if package["pypi_version"] is not None:
            release_version(package["pypi_version"])
        exact_fields(entry["evidence"], "report synthetic meds_dev clinical_demo full_dataset", "evidence")
        report = text(entry["evidence"]["report"], "report")
        if not re.fullmatch(r"[A-Za-z0-9_./-]+\.md", report) or any(
            p in ("", ".", "..") for p in report.split("/")
        ):
            raise ValueError("Report must be a repository-relative Markdown file")
        for field, value in entry["evidence"].items():
            if field != "report" and value not in VALIDATION_LABELS:
                raise ValueError(f"Unknown validation status for {field}")
    return data["algorithms"]


def render_catalogue(entries):
    sections = []
    for entry in entries:
        repository = entry["repository"]
        revision = entry["revision"]
        source = f"{repository}/tree/{revision}"
        report = f"{repository}/blob/{revision}/{entry['evidence']['report']}"
        access = "Private — access required" if entry["access"] == "private" else "Public"
        parts = [
            f'<h2 id="{entry["id"]}">{escape(entry["name"])}</h2>',
            f"<p>{escape(entry['description'])}</p>",
            f"<p><strong>{STATUS_LABELS[entry['implementation_status']]}</strong> · {access}</p>",
            f'<p><a href="{escape(repository, quote=True)}">Repository</a> · '
            f'<a href="{escape(source, quote=True)}">Reviewed revision {revision[:7]}</a> · '
            f'<a href="{escape(report, quote=True)}">Implementation report</a></p>',
        ]
        if entry["paper"]:
            parts.append(f'<p><a href="{escape(entry["paper"], quote=True)}">Paper</a></p>')
        if entry["implementation_pr"]:
            parts.append(
                f'<p><a href="{repository}/pull/{entry["implementation_pr"]}">Implementation PR</a></p>'
            )
        parts.append(
            f"<p>Declared profiles: <code>{', '.join(entry['profiles'])}</code>. "
            f"Metadata reviewed: {entry['reviewed_on']}.</p>"
        )
        package = entry["package"]
        name, version = package["name"], package["pypi_version"]
        if version is None:
            parts.append(
                f"<p>Declared package name: <code>{name}</code>. No reviewed PyPI release; "
                "no PyPI installation command is advertised.</p>"
            )
        else:
            parts.append(
                f'<p><a href="https://pypi.org/project/{name}/{quote(version)}/">'
                f"{name} {version} on PyPI</a></p>"
            )
            parts.append(f'<pre><code>python -m pip install "{name}=={version}"</code></pre>')
        parts.append(
            "<table><thead><tr><th>Validation at the reviewed revision</th>"
            "<th>Evidence</th></tr></thead><tbody>"
        )
        for field, label in (
            ("synthetic", "Synthetic/local"),
            ("meds_dev", "MEDS-DEV integration"),
            ("clinical_demo", "Clinical demo"),
            ("full_dataset", "Full dataset"),
        ):
            parts.append(f"<tr><td>{label}</td><td>{VALIDATION_LABELS[entry['evidence'][field]]}</td></tr>")
        parts.append(f"</tbody></table><p>{escape(entry['notes'])}</p>")
        sections.append("\n".join(parts))
    return "\n\n".join(sections) or "No algorithms have been registered yet."


def on_page_markdown(markdown, page, **kwargs):
    if page.file.src_uri == "implemented-algorithms.md":
        entries = load_catalogue(ROOT / "catalogue/algorithms.yaml")
        return markdown.replace("<!-- algorithm-catalogue -->", render_catalogue(entries))
    return markdown


def fetch_json(url):
    # Public metadata only. Do not send GitHub credentials or clone/import any algorithm.
    request = Request(url, headers={"User-Agent": "MEDS-algorithm-catalogue", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        if error.code == 404:
            return None
        raise  # Rate limits/network failures are errors, never evidence of an unavailable package.


def observe_releases(entries, fetch=fetch_json):
    observations = {}
    for entry in entries:
        observation = {"repository": "private_manual_review", "latest_github_release": None}
        if entry["access"] == "public":
            api = "https://api.github.com/repos/" + entry["repository"].removeprefix("https://github.com/")
            repository = fetch(api)
            observation["repository"] = "available" if repository else "unavailable_or_private"
            if repository:
                release = fetch(api + "/releases/latest")
                observation["latest_github_release"] = release.get("tag_name") if release else None
        name = entry["package"]["name"]
        metadata = fetch(f"https://pypi.org/pypi/{name}/json")
        available = []
        if metadata:
            for version, files in metadata.get("releases", {}).items():
                try:
                    parsed = release_version(version)
                except ValueError:
                    continue
                if any(not file.get("yanked", False) for file in files):
                    available.append((parsed, version))
        pinned = entry["package"]["pypi_version"]
        observation.update(
            pypi="available" if metadata else "not_found",
            latest_pypi_release=max(available)[1] if available else None,
            reviewed_pypi_release=pinned,
            reviewed_release_available=any(version == pinned for _, version in available) if pinned else None,
        )
        observations[entry["id"]] = observation
    return {"schema_version": 1, "observations": observations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=ROOT / "catalogue/algorithms.yaml")
    parser.add_argument("--check-remote", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "catalogue/updates.json")
    args = parser.parse_args()
    entries = load_catalogue(args.registry)
    if args.check_remote:
        result = observe_releases(entries)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Release observations written to {args.output}; curated evidence was not changed.")
    else:
        print(f"Validated {len(entries)} catalogue entries offline.")


if __name__ == "__main__":
    main()
