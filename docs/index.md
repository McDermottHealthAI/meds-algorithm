# MEDS algorithms

`meds-algorithm` provides shared contracts and infrastructure for algorithms consuming MEDS data:
profile interfaces, typed step requests, artifact provenance, prediction validation and conformance tests.

- Browse [implemented algorithms](implemented-algorithms.md), their declared profiles, reviewed PyPI
  versions and validation evidence.
- Read the [package README](https://github.com/McDermottHealthAI/meds-algorithm#readme),
  [architecture and UML](https://github.com/McDermottHealthAI/meds-algorithm/blob/main/ARCHITECTURE.md),
  and [canonical contract](https://github.com/McDermottHealthAI/meds-algorithm/blob/main/src/meds_algorithm/CONTRACT.md).
- Build an implementation using the
  [algorithm template and its workflow documentation](https://mcdermotthealthai.github.io/MEDS_algorithm_template/).

The catalogue belongs to this ecosystem repository and is maintained independently of Python package
releases. Its registry, renderer and tests are excluded from both wheel and source distributions.
Updating a listing rebuilds this site; it does not require publishing another `meds-algorithm` version.

## Maintaining this documentation

```bash
uv sync --locked --group docs
uv run --group docs pytest docs/tests -q
uv run --group docs mkdocs serve
```

See [catalogue registration and updates](implemented-algorithms.md#register-or-update-an-algorithm) and
the [catalogue test inventory](catalogue-testing.md). Runtime tests remain under `tests/` and their
inventory remains in the packaged
[TESTING.md](https://github.com/McDermottHealthAI/meds-algorithm/blob/main/src/meds_algorithm/TESTING.md).

### Read the Docs hosting

The repository-root `.readthedocs.yaml` builds this site with Python 3.12, the existing `docs`
dependency group and MkDocs Material. It uses uv to install dependencies from `pyproject.toml` and
`uv.lock`, and fails on documentation warnings. GitHub Actions continues running catalogue tests,
validation, lint and the strict documentation build independently of the hosting service.

To enable hosting:

1. Import `McDermottHealthAI/meds-algorithm` into Read the Docs and use `meds-algorithm` as the project
   slug. If a different slug is needed, update the README badge and links, `pyproject.toml` documentation
   URL and the fallback `site_url` in `mkdocs.yml` together.
2. Set the default branch to `main`, build its `latest` version, and use `latest` as the default
   documentation version initially. Older release tags do not contain this hosting configuration.
3. Verify the build and the catalogue at
   <https://meds-algorithm.readthedocs.io/en/latest/>, and enable pull request builds if desired.

MkDocs reads `READTHEDOCS_CANONICAL_URL` during hosted builds so canonical links use the appropriate
version URL. Local builds fall back to the `latest` URL. The source pages, navigation and theme are
shared between local builds and hosting; no second copy of the documentation is needed.

### GitHub Pages transition

The existing GitHub Pages deployment remains active until Read the Docs has built successfully.
After verifying the new site, replace the Pages publication with a small redirect site that preserves
the old page paths and fragments at <https://mcdermotthealthai.github.io/meds-algorithm/>. Keep those
redirects hosted on Pages so existing links continue working; Read the Docs cannot redirect requests
made to the old GitHub Pages domain. Retain the GitHub Actions documentation checks when replacing
the old full-site deployment.

This change only moves hosting for this repository. The algorithm template's documentation remains
at its existing GitHub Pages URL.

The weekly catalogue workflow additionally needs permission for Actions to create pull requests; its
registration guide documents the setting and the report-artifact fallback. No private-repository
credentials are required.
