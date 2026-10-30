# Publishing meds-algorithm and its template

Publish **meds-algorithm first**, then **meds-algorithm-template**. Moving GitHub repositories does not
create or transfer PyPI projects. These steps assume the preparation PRs have been reviewed and merged
into each repository's `main`. No package is uploaded by normal CI, a push, or creating a tag.

## 1. Configure accounts and Trusted Publishers

Use the PyPI account that should own the projects. Enable its required two-factor authentication and
configure a pending publisher at [PyPI publishing](https://pypi.org/manage/account/publishing/), and
separately at [TestPyPI publishing](https://test.pypi.org/manage/account/publishing/).
If a project already exists under your account, add a publisher in that project's Publishing settings.
A pending publisher does not reserve a name; check availability before the first upload.

Use these exact values on **both indexes**:

| Field | Shared package | Template generator |
|---|---|---|
| PyPI project | `meds-algorithm` | `meds-algorithm-template` |
| GitHub owner | `McDermottHealthAI` | `McDermottHealthAI` |
| GitHub repository | `meds-algorithm` | `MEDS_algorithm_template` |
| Workflow filename | `publish.yml` | `publish.yml` |
| Environment on TestPyPI | `testpypi` | `testpypi` |
| Environment on PyPI | `pypi` | `pypi` |

The GitHub repository spelling and the PyPI distribution spelling are intentionally different for the
template. PyPI project ownership is independent of GitHub organization membership; add the appropriate
maintainers or PyPI organization separately.

An organization repository administrator must configure the `testpypi` and `pypi` GitHub environments
under Settings → Environments in both repositories. Restrict deployment to reviewed release tags
(`v*`) and add a required reviewer for `pypi`. The transferred account currently has write access;
administering environments may require an organization owner. No PyPI API token or GitHub secret is
needed with Trusted Publishing. The workflows grant `id-token: write` only to the upload job.

See the official [pending-publisher setup](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
and [publishing action](https://docs.pypi.org/trusted-publishers/using-a-publisher/) documentation.

## 2. Release the shared package first

Current candidate: **0.4.0a4**. Run the following in Bash/WSL with Git, GitHub CLI and uv installed.
Use the reviewed `main` commit, and wait for its CI checks before tagging. Do not move or reuse a
published release tag/version; increment `project.version` for a replacement.

```bash
git clone https://github.com/McDermottHealthAI/meds-algorithm.git
cd meds-algorithm
git switch main
git pull --ff-only
uv sync --locked --extra test --group dev
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv build
uvx --from 'twine>=6' twine check --strict dist/*
git tag v0.4.0a4
git push origin v0.4.0a4

gh workflow run publish.yml --repo McDermottHealthAI/meds-algorithm \
  --ref v0.4.0a4 -f index=testpypi
gh run list --repo McDermottHealthAI/meds-algorithm --workflow publish.yml --limit 5
# Select the run created above and watch it:
gh run watch RUN_ID --repo McDermottHealthAI/meds-algorithm --exit-status
```

The workflow checks that the tag equals `v` plus `project.version` and belongs to `main` history. It
runs lint/tests, builds from source, checks distribution metadata, installs the standalone wheel and
runs its smoke checks before uploading. Distributions are retained as the `distributions` Actions
artifact. Each TestPyPI/PyPI invocation rebuilds from the same tag; it does not promote the previous
run's exact archive bytes.

Verify the TestPyPI installation in a clean environment, installing dependencies from PyPI separately:

```bash
check_env=$(mktemp -d)
uv venv "$check_env"
uv pip install --python "$check_env/bin/python" 'pyyaml>=6'
uv pip install --python "$check_env/bin/python" --no-deps \
  --index-url https://test.pypi.org/simple/ 'meds-algorithm==0.4.0a4'
"$check_env/bin/python" -I tests/wheel_smoke.py
uv pip check --python "$check_env/bin/python"
```

After the test release is verified, publish the same tag to PyPI and approve its environment deployment:

```bash
gh workflow run publish.yml --repo McDermottHealthAI/meds-algorithm \
  --ref v0.4.0a4 -f index=pypi
# Find and watch the new run as above. After it succeeds:
pypi_env=$(mktemp -d)
uv venv "$pypi_env"
uv pip install --python "$pypi_env/bin/python" 'meds-algorithm==0.4.0a4'
"$pypi_env/bin/python" -I tests/wheel_smoke.py
uv pip check --python "$pypi_env/bin/python"
```

Keep TestPyPI and PyPI separate; do not combine them with an extra index for dependency resolution.
See the official [TestPyPI guide](https://packaging.python.org/en/latest/guides/using-testpypi/).

## 3. Cut over and release the template

Only after `meds-algorithm==0.4.0a4` installs from PyPI, follow the
[template release guide](https://github.com/McDermottHealthAI/MEDS_algorithm_template/blob/main/RELEASING.md).
It switches the development and generated dependencies from the Git pin to the released package,
updates the lockfile/docs, and publishes the generator at **0.4.0a1** with tag **v0.4.0a1**.
Its release preflight deliberately refuses publication until that cutover is complete.

## 4. After first publication

Replace each README's `PyPI-unreleased-lightgrey` badge with
`https://img.shields.io/pypi/v/meds-algorithm` or
`https://img.shields.io/pypi/v/meds-algorithm-template`, linking to the corresponding PyPI project.
If the default badge omits an alpha release, use the Shields `include_prereleases` option.
Update the install instructions from candidate/future wording to the verified release. Keep alpha
versions explicit in install commands. No model-repository migrations are performed by publishing.
