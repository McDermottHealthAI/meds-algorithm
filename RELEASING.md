# Releasing meds-algorithm-core

Release validation has three stages: validate the distributions, rehearse delivery through TestPyPI,
then verify installation from PyPI. Package validation does not replace scientific validation of
downstream algorithms.

## Distribution checks

CI runs lint and tests on Python 3.11, 3.12 and 3.13, then builds a source distribution and a wheel
with `uv build` (the wheel is built from the source distribution). It also:

- Runs `twine check --strict` on both distributions to validate metadata and README rendering.
- Installs the base wheel in a fresh environment, without Polars or pytest, and exercises all three
  installed CLI entry points, the packaged contract and artifact publication.
- Installs the `conformance` extra and runs the test suite from outside the checkout against that
  wheel, with isolated Python imports, followed by dependency compatibility checks.
- Exercises the base wheel on Windows as well as Linux.

Before the first index release, generate both a single-profile repository and a repository containing
all six profiles from the template. Install their wheels with the candidate core distribution and
run their registry and operational tests. Confirm that the generated wheel does not contain a copy
of `meds_algorithm_core` or `meds_algorithm_contract`, and that the documentation builds with the installed
contract. These checks validate template integration; generated algorithm methods are still skeletons.

## TestPyPI rehearsal

Use a fresh output directory so distributions from earlier versions cannot be uploaded accidentally.
The following commands assume Bash, `uv`, and an authenticated upload configuration. Run from the
core checkout; substitute the candidate version when it changes.

```bash
release_dir=$(mktemp -d)
uv build --out-dir "$release_dir"
uvx --from 'twine>=6' twine check --strict "$release_dir"/*
uvx --from 'twine>=6' twine upload --repository testpypi "$release_dir"/*

test_env=$(mktemp -d)
uv venv "$test_env"
uv pip install --python "$test_env/bin/python" 'pyyaml>=6'
uv pip install --python "$test_env/bin/python" \
  --index-url https://test.pypi.org/simple/ --no-deps 'meds-algorithm-core==0.3.0a3'
"$test_env/bin/python" -I tests/wheel_smoke.py
uv pip check --python "$test_env/bin/python"
```

Install dependencies from PyPI separately. Do not rely on TestPyPI containing them or combine the
two indexes for dependency resolution. Inspect the TestPyPI project page for the expected README,
version, license, extras and files. Compare downloaded wheel and source-distribution SHA-256 hashes
with the local candidates before promoting those same files to PyPI.

TestPyPI has separate accounts and publisher configuration from PyPI. Uploads are not part of normal
CI. See the [official TestPyPI guide](https://packaging.python.org/en/latest/guides/using-testpypi/).

## Publishing setup and promotion

Prefer GitHub Actions Trusted Publishing. It requires a publisher configured on the index and a
matching release workflow in this repository; neither an ordinary CI run nor a GitHub repository
alone grants permission to publish. A new project can use a pending publisher. Configure PyPI and
TestPyPI separately, with the following proposed values when adding the release workflow:

| Field | PyPI | TestPyPI |
| --- | --- | --- |
| Project | `meds-algorithm-core` | `meds-algorithm-core` |
| GitHub owner | `florian6973` | `florian6973` |
| Repository | `meds-algorithm-core` | `meds-algorithm-core` |
| Workflow filename | `publish.yml` | `publish.yml` |
| GitHub environment | `pypi` | `testpypi` |

The release workflow should upload the tested distributions with
`pypa/gh-action-pypi-publish`, grant `id-token: write` only to publishing jobs, and promote the same
verified files after the TestPyPI installation check. This workflow is not installed yet.
See [PyPI's Trusted Publishing setup](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
and [publishing instructions](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

After publishing, repeat the clean-environment installation with the default PyPI index and the exact
version, then switch the template's Git dependency to `meds-algorithm-core==<version>` (retaining its
`conformance` extra where needed). Update the lockfile, rerun generated-project checks and rebuild the
documentation preview. Alpha versions require an explicit version pin or prerelease selection.
