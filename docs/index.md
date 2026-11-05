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

GitHub Actions builds and checks the site on PRs and deploys pushes to `main`. For the first deployment,
configure **Settings → Pages → Build and deployment → Source: GitHub Actions**. The weekly catalogue
workflow additionally needs permission for Actions to create pull requests; its registration guide
documents the setting and the report-artifact fallback. No private-repository credentials are required.
