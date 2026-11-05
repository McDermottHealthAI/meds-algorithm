# Implemented algorithms

This catalogue records implementations and their review status, including work under review. Listing is
not a claim of clinical validation. Profiles are declared capabilities; validation is summarized separately
from the linked implementation report at an immutable revision. “Pass reported” means the report records
a passing run, not that the catalogue build reran it.

Published entries include their PyPI name and an exact-version installation command. An unpublished
package name is only the name declared in its repository; it is not reserved on PyPI. Private entries
are explicitly approved public metadata listings; their source and evidence links still require access.

<!-- algorithm-catalogue -->

## Register or update an algorithm

Open a PR editing `catalogue/algorithms.yaml` in the `meds-algorithm` repository. Copy an entry and supply:

- A stable ID, display name, short description, repository access level and optional paper URL.
- The declared profiles and implementation status; include the PR number for work under review.
- The full commit SHA examined, date of metadata review and report path at that commit.
- The distribution name from `pyproject.toml`. Leave `pypi_version: null` until a release is actually
  on PyPI and its ownership, source revision and validation evidence have been checked. Set an exact
  reviewed version to generate its install command; do not set it merely because the name exists on PyPI.
- Separate evidence statuses for synthetic/local tests, MEDS-DEV, clinical demo and full-dataset runs:
  `reported_pass`, `pending`, `not_run`, `failed`, or `not_reported`. Link the evidence rather than copying
  private results, dataset descriptions or logs into the registry.
- `public_listing: true` only after the owner authorizes these metadata for public documentation.

The schema accepts `implemented`, `in_review`, and `in_progress` implementation states. Profile names come
from the installed core contract. Keep one entry per repository even when it supports several profiles.
When updating a reviewed version, recheck its commit and evidence; a newer package is not automatically
validated. The registry is the single source for this page, including the install commands.

```bash
uv sync --group docs
uv run python docs/catalogue.py
uv run --group docs mkdocs build --strict
```

## Keeping the catalogue current

Normal docs builds and PR checks validate the committed registry offline. They do not fetch private
repositories, install algorithms, or require GitHub credentials.

The **Catalogue updates** workflow runs weekly and can be dispatched manually. It checks public GitHub
repository availability/latest stable release and PyPI release availability, including prereleases and
yanked files. It skips private repository queries entirely. PyPI checks still use the approved public
package name. A network/rate-limit failure fails the job rather than marking the package missing.

```bash
uv run python docs/catalogue.py --check-remote
gh workflow run catalogue.yml --repo McDermottHealthAI/meds-algorithm
```

The workflow writes `catalogue/updates.json` and opens or updates one PR only when observations change.
It does not change reviewed versions, implementation status or evidence. There is no timestamp churn.
Maintainers inspect that PR and separately update the curated entry after reviewing the new release.
The observation report is advisory; it neither establishes package ownership nor changes install commands.

To enable update PRs after merging this workflow into `main`, allow GitHub Actions to create pull requests
under **Settings → Actions → General → Workflow permissions** (the organization may control this setting).
The workflow requests contents/PR write access only for its update job. The default `GITHUB_TOKEN` does
not trigger other PR workflows; this job runs registry tests and a strict docs build itself before opening
its report PR. A maintainer can run checks locally before changing curated entries. See the
[action's permission and token documentation](https://github.com/peter-evans/create-pull-request#workflow-permissions).
The workflow also uploads its report as an artifact, so observations remain available if PR creation is
disabled. Private entries need manual source/evidence review by someone with access.
