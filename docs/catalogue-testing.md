# Catalogue tests

These repository-level tests validate documentation and release discovery. They are separate from the runtime package tests and are not shipped in its distributions.

`uv run --group docs pytest docs/tests -q`

### test_catalogue.py

| Test | What it checks | Why it exists |
|---|---|---|
| `test_private_unpublished_entry_renders_without_network` | Renders the pinned GenHPF entry with access/status labels, without fetching metadata or inventing an install command. | Keep public docs builds independent of private access and distinguish declared names from published distributions. |
| `test_published_entry_generates_escaped_pinned_install_command` | Generates a version-pinned PyPI link/command and escapes names/notes as HTML. | Make installation reproducible and keep registry content inert. |
| `test_registry_rejects_ambiguous_or_unsafe_entries` | Rejects moving revisions, unknown profiles/states, duplicate profiles, unapproved listings, invalid URLs and review dates. | Require an auditable registration record. |
| `test_registry_rejects_invalid_install_or_evidence_fields` | Rejects malformed package names/versions, traversing report paths and unknown evidence statuses. | Prevent unsafe commands and ambiguous evidence links. |
| `test_registry_rejects_duplicates_and_unknown_fields` | Rejects duplicate IDs and unrecognized schema fields. | Catch copy/paste errors and misspelled metadata. |
| `test_release_observer_skips_private_source_and_never_changes_evidence` | Detects public PyPI candidates, ignores yanked/empty releases, skips private GitHub access, and produces stable observations without mutating entries. | Keep release discovery separate from scientific review and avoid timestamp-only PRs. |
| `test_missing_public_repository_and_yanked_reviewed_release_are_observed` | Records unavailable repositories and yanked reviewed releases. | Surface broken availability without silently choosing a replacement. |
| `test_public_github_release_and_absent_pypi_are_observed` | Observes a public GitHub release independently of PyPI availability. | A GitHub tag/release is not proof of an installable PyPI distribution. |
| `test_network_errors_are_not_missing_release_evidence` | Propagates server/rate-limit errors and verifies requests omit credentials. | Avoid false disappearance reports and private-source access. |
| `test_observation_snapshot_contains_only_metadata` | Checks the committed observation snapshot corresponds to registered entries. | Keep the example snapshot valid and separate from implementation reports. |

