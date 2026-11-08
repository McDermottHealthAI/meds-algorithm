# Maintaining documentation

The full MEDS algorithms site is maintained in `McDermottHealthAI/meds-algorithm` and hosted at
<https://meds-algorithm.readthedocs.io/en/latest/>. `latest` follows core `main`; it may describe changes
newer than the released core version pinned by an algorithm. Use its installed contract for that version.

## One maintained source per document

| Content | Canonical source |
|---|---|
| Concepts, profiles, workflow, tutorials, prompt builder and static prompt | This repository's `docs/` |
| Contract, architecture/UML, shared tests and orchestration | Core's `src/meds_algorithm/*.md` and `ARCHITECTURE.md`, rendered directly from this checkout |
| Catalogue | `catalogue/algorithms.yaml` and `catalogue/updates.json` |
| Template contributor release/test guides | `RELEASING.md` and `TESTING.md` in the template repository |
| Generated algorithm release/test guides | `template/RELEASING.md.jinja` and `template/docs/TESTING.md` in the template repository |

The last two rows are included at build time from the immutable template commit recorded in
`docs/template-source.json`. Each file is SHA-256 checked and cached under `.cache/template-docs/`.
Only these public documentation files are fetched; the build does not clone private algorithms or run
template code. A missing source or checksum mismatch fails the build. The cached files permit offline
rebuilds, but a clean checkout needs network access for its first build.

When template-owned guides change, update the revision and four hashes in `docs/template-source.json`
in a core PR, then run the strict build. Keep their content in the template so generated projects and
the documentation use the same instructions. Do not copy those files into this repository.

The static implementation prompt lives in `docs/implementation-prompt.md`; the interactive builder embeds
its text block. Edit that single source to update both. Template README links point here.

## Local checks and preview

From the root of this core checkout:

```bash
uv sync --locked --group docs
uv run --group docs pytest -q docs/tests
uv run ruff check docs scripts
uv run ruff format --check docs scripts
npm ci --ignore-scripts
npm test
uv run --group docs mkdocs build --strict
uv run --group docs mkdocs serve
```

Node 24 is needed only for browser tests, not for building or serving the site. See
[documentation tests](documentation-tests.md) and [catalogue tests](catalogue-testing.md) for what each checks.
Runtime tests remain under `tests/`; their inventory is [Shared-package tests](reference/tests.md).

## Hosting and old links

Read the Docs builds with `.readthedocs.yaml`, Python 3.12, uv's `docs` dependency group and MkDocs Material.
`READTHEDOCS_CANONICAL_URL` supplies the version-specific canonical URL, with a `latest` fallback locally.
GitHub Actions runs documentation checks independently. Enable Read the Docs pull request builds in the
project settings for hosted previews. Older release tags without this configuration cannot build this site.

Both retired GitHub Pages sites now publish redirect pages, not a second documentation build:

- `https://mcdermotthealthai.github.io/meds-algorithm/`
- `https://mcdermotthealthai.github.io/MEDS_algorithm_template/`

Keep Pages enabled in both repositories. `scripts/build_docs_redirects.py` creates files for known old
routes listed in `redirects/paths.json` and a 404 fallback for other deep links. The redirect preserves
the page path, query and section fragment. A visible Read the Docs link remains when JavaScript is disabled.
The template workflow only publishes these redirects; all MkDocs and prompt tests run here.

The catalogue update workflow still needs permission for Actions to create pull requests; see
[catalogue maintenance](implemented-algorithms.md#register-or-update-an-algorithm) for its report fallback.
