# Documentation tests

Documentation tests run separately from the installed runtime suite. They do not train algorithms,
access clinical data, or establish scientific validity.

Run `uv run --group docs pytest -q docs/tests` and, with Node 24, `npm ci --ignore-scripts && npm test`.
The strict MkDocs build additionally validates page links, anchors, snippets, template-source hashes
and rendered reference pages. See [site maintenance](documentation.md) for the full commands.

## Python source and rendering tests

| Test | What it checks | Why |
|---|---|---|
| Canonical prompt embedding | Decodes embedded JSON and compares it with the static prompt's text block | Keep the copyable and interactive prompts identical |
| Release guide rendering | Renders the template source with example package names | Avoid showing unresolved Jinja placeholders |
| Script boundary escaping | Embeds prompt text containing a script closer | Keep source text inert inside HTML |
| Core reference sources | Compares contract, UML, test catalogue and orchestration with this checkout | Prevent stale installed-wheel docs from masking code changes |
| Immutable source and cache | Checks the requested commit URL and verifies a cache hit avoids another fetch | Make template-owned guides reproducible and support offline rebuilds |
| Corrupt downloaded/cached sources | Rejects content whose SHA-256 differs from the manifest | Never silently publish changed source content |
| Mutable revision rejection | Rejects a branch name instead of a full commit SHA | Keep builds independent of moving template branches |
| Download failure | Propagates unavailable-source errors | Fail instead of substituting stale or unrelated guidance |

The [catalogue test inventory](catalogue-testing.md) documents its separate registry checks.

## Browser tests

The prompt builder uses plain JavaScript with no runtime dependencies, network requests or persisted
form inputs. jsdom is used only in tests.

| Test | What it checks | Why |
|---|---|---|
| All 144 input combinations | Source, destination, profiles, task bundle, scope and ambiguity mode | Preserve the user's choices and scientific/execution gates |
| Ambiguity defaults | Missing/false mode requires confirmation; non-booleans fail | Prevent accidental exploratory opt-in |
| Checkbox lifecycle | Unchecked initial state, explicit toggle, stale output and reset | Keep exploratory mode intentional |
| Invalid plans | Missing sources, destination, profiles and prepared-task metadata | Avoid apparently executable incomplete prompts |
| Task subsets and literal text | Existing task identifiers and non-recursive substitutions | Preserve supplied scope and constraints |
| Conditional fields | Visibility, required fields and several selected profiles | Prevent hidden inputs from overriding user choices |
| Edits, copy, download, reset | Exact edited text and stale-output invalidation | Prevent copying outdated instructions |
| Clipboard fallback | Selection after denied clipboard access | Support local previews and restricted browser contexts |
| Inert HTML and repeated initialization | HTML-like user text and repeated page initialization | Prevent injection and lost edits |
