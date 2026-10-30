# Shared-package test catalogue

This is the test inventory for the source version shipped with this package. Each row names a test
function, describes its observable check and explains the failure it prevents. Parametrized functions
run multiple cases, so the number of pytest results is larger than the number of rows.

## Running the tests

From a development checkout:

```bash
uv sync --extra test --group dev
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run pytest tests/test_algorithms.py -q
uv run pytest -k fitted_request_schema -q
```

The suite uses synthetic files and toy algorithms; it does not download clinical data or train a real
model. The Linux process-tree test is skipped elsewhere. Subprocess and filesystem tests exercise real
local processes and temporary files. The default suite does not opt in to MEDS-DEV or MIMIC provisioning.

Passing establishes the checked software boundaries, not clinical validity, numerical equivalence to a
paper, GPU correctness or absence of all leakage. Algorithm repositories must supply scientific tests,
cutoff/frozen-weight checks and end-to-end adapters for their concrete implementations. The label-blind
rerun is an adversarial check, not a filesystem sandbox or proof against malicious code.

## Test inventory

### test_algorithms.py

[Source](https://github.com/McDermottHealthAI/meds-algorithm/blob/main/tests/test_algorithms.py)

| Test | What it checks | Why it exists |
|---|---|---|
| `test_configuration_is_strict_immutable_and_roundtrips` | Checks nested defaults, immutability, invalid fields/types/values and exact-class reloads. | Prevent silent configuration drift and accidental coercion. |
| `test_runner_publishes_resolved_config_and_request` | Checks saved config/request, upstream and index digests, final destination and post-score truth. | Make outputs reproducible and auditable without exposing truth to scoring. |
| `test_incomplete_recorded_configuration_is_rejected` | Removes a resolved field from fitted-input provenance and requires failure before publication. | Do not silently interpret historical configuration as the current configuration. |
| `test_reloaded_request_runs_in_a_fresh_process` | Reloads configuration and a request in a subprocess and compares predictions. | Ensure inference depends on persisted artifacts rather than previous calls on one object. |
| `test_runner_validates_before_algorithm_and_preserves_previous_output` | Rejects incompatible config and injects invalid replacement predictions. | Catch errors before publication and preserve a previous valid artifact. |
| `test_request_types_and_paths_cannot_cross_boundaries` | Rejects the wrong request, overlapping output, unknown arguments and forbidden labels; exercises CLI dispatch. | Keep the public execution boundary explicit and prevent destructive or label-leaking invocations. |
| `test_profile_requests_are_the_source_of_step_metadata` | Compares every profile's lifecycle and request outputs with derived step specifications. | Prevent metadata from drifting away from the typed interfaces. |
| `test_profile_abcs_require_complete_implementations` | Rejects abstract implementations and classes registered under the wrong profile. | Fail incomplete or misdeclared algorithms before execution. |
| `test_config_file_resolves_paths_and_rejects_unsupported_values` | Checks relative path resolution, file loading and unsupported mutable/nonfinite values. | Keep saved settings portable relative to their file and strictly serializable. |
| `test_version_four_rejects_old_artifact_and_argument_names` | Rejects old contract versions, artifact names and model-named CLI inputs. | Require an explicit migration instead of accepting incompatible envelopes. |
| `test_predict_only_context_must_be_explicit_and_disjoint` | Checks permitted context splits and rejects overlap with evaluated keys. | Prevent in-context examples from containing evaluated outcomes. |
| `test_invalid_algorithm_metadata_or_ground_truth_never_publishes` | Injects invalid payload metadata, reserved provenance files and algorithm-written truth. | Keep publication and evaluation ownership in the runner. |
| `test_sharded_predictions_validate_complete_key_set` | Checks predictions distributed across shards against the full expected index. | Do not validate only one shard or silently omit expected predictions. |
| `test_every_profile_runs_through_typed_cli_adapter` | Executes all six profile lifecycles through the typed repository adapter. | Prove the shared dispatcher supports every declared lifecycle, not only supervised learning. |
| `test_fitted_request_schema_rejects_old_envelopes_and_field_names` | Round-trips each renamed prediction request, then rejects schema 1 and the old algorithm field. | Make the fitted_algorithm rename explicit for persisted requests while retaining CLI names. |
| `test_removed_dispatchers_are_not_public_execution_paths` | Checks that Command and LegacyAlgorithmRepository are absent from both exports and implementation. | Prevent reintroducing a second dispatch path that bypasses the typed runner. |

### test_artifacts.py

[Source](https://github.com/McDermottHealthAI/meds-algorithm/blob/main/tests/test_artifacts.py)

| Test | What it checks | Why it exists |
|---|---|---|
| `test_body_failure_and_existing_destination_preserve_previous_artifact` | Rejects an existing destination without overwrite and injects a failure inside publication. | Keep previous output intact and clean up unsuccessful staging. |
| `test_publication_failure_retains_old_artifact` | Injects publication-rename failure, with successful or failed restoration. | Preserve the only valid old copy even when filesystem recovery also fails. |
| `test_unique_staging_and_exclusive_destination_lock` | Attempts concurrent writers and repeated publications to the same destination. | Prevent writers from sharing staging space or racing over an artifact. |
| `test_manifest_write_failure_keeps_previous_artifact` | Injects YAML manifest serialization failure during replacement. | Treat metadata failure as an unsuccessful publication, preserving the previous artifact. |
| `test_algorithm_provenance_is_explicit_and_unknown_outside_checkout` | Uses an explicit Git checkout, dirty changes and absent checkout paths. | Never attribute the core package or working directory's revision to the algorithm. |
| `test_process_tree_includes_worker_thread_children` | Launches a child process from a worker thread and checks Linux process-tree discovery. | Include memory used by worker-launched subprocesses; Linux-only because it tests /proc. |
| `test_unavailable_resource_measurement_is_reported_honestly` | Disables the fallback resource API and checks null values and unavailable status. | Avoid reporting missing measurements as zero or complete process-tree coverage. |
| `test_upstream_resolution_and_result_identity` | Resolves a recorded relative upstream path and rejects a mislabeled run artifact. | Keep run summaries and recovered inputs tied to the correct step. |
| `test_invalid_manifest_and_publication_type_fail_before_use` | Corrupts an artifact/command type association and attempts incompatible publication. | Reject invalid envelopes before consumers or algorithm work use them. |

### test_configuration.py

[Source](https://github.com/McDermottHealthAI/meds-algorithm/blob/main/tests/test_configuration.py)

| Test | What it checks | Why it exists |
|---|---|---|
| `test_nn_config_subclass_roundtrip_and_capacity_sweep` | Exercises a concrete neural config, serialization, defaults and capacity-to-width mapping. | Demonstrate that scaling controls can remain typed, immutable and reproducible. |
| `test_nn_config_rejects_invalid_values_from_python_and_files` | Parametrizes wrong types, nonfinite and out-of-range neural settings. | Enforce the same invariants for Python construction and decoded configuration. |
| `test_nn_config_requires_explicit_training_settings` | Rejects missing learning rate/batch size and checks classical config independence. | Do not invent universal training defaults or require neural settings for classical algorithms. |
| `test_repository_records_nn_settings_from_config_file` | Dispatches with a file override and checks resolved saved config and manifest. | Ensure experiment settings actually reach the algorithm and persisted provenance. |

### test_conformance.py

[Source](https://github.com/McDermottHealthAI/meds-algorithm/blob/main/tests/test_conformance.py)

| Test | What it checks | Why it exists |
|---|---|---|
| `test_optional_label_leakage_changes_scores_and_fails` | Runs a deliberately leaky predictor with outcomes removed on rerun. | Detect scores that depend on forbidden outcomes even when labels are treated as optional. |
| `test_original_invalid_scores_fail_before_rerun` | Injects NaN, infinity and out-of-range scores into the original run. | Do not let a clean rerun hide invalid original predictions. |
| `test_sharded_predictions_and_separate_training_roots` | Checks nested prediction shards with separate training and evaluation roots. | Support realistic layouts while retaining allowed training targets during leakage checks. |
| `test_reproducible_seed_is_required` | Removes the recorded seed before a conformance rerun. | Avoid confusing randomness with evidence of label leakage. |
| `test_shared_conformance_runs_each_profile_from_fresh_outputs` | Runs shared conformance on each profile with new artifact destinations. | Apply lifecycle guarantees consistently across all supported profiles. |
| `test_full_lifecycle_check_catches_labels_read_before_prediction` | Injects forbidden outcome access during an earlier pipeline stage. | Detect leakage in preprocessing or fitting, not just the final prediction method. |
| `test_full_lifecycle_check_rejects_cached_outputs` | Returns the original artifacts instead of rebuilding the label-blind lifecycle. | Prevent cached predictions from making the leakage test pass without exercising the algorithm. |

### test_core.py

[Source](https://github.com/McDermottHealthAI/meds-algorithm/blob/main/tests/test_core.py)

| Test | What it checks | Why it exists |
|---|---|---|
| `test_index_reader_projects_keys_at_io_boundary` | Records requested Parquet columns and confirms only subject/time keys are loaded. | Avoid loading outcomes into prediction input in the first place. |
| `test_split_selection_rejects_partial_coverage_and_mislabelled_single_file` | Checks missing splits, ambiguous files and explicitly named shards. | Never silently broaden or reduce the caller's requested split selection. |
| `test_index_reader_rejects_duplicate_and_missing_key_schemas` | Builds duplicate-key shards and files lacking required keys. | Make the prediction index a unique, well-defined set of examples. |
| `test_roles_distinguish_ground_truth_from_prediction_keys` | Inspects derived arguments and label permissions for inference and prediction. | Keep outcome labels separate from keys and require the appropriate prepared inputs. |
| `test_specification_is_an_installed_package_resource` | Reads the normative specification and test catalogue through package resources. | Ensure wheel users receive the canonical documentation without a repository checkout. |
| `test_conflicting_split_names_never_select_evaluation_as_training` | Uses a shard whose directory and filename indicate different splits. | Fail ambiguous provenance instead of treating evaluation data as training data. |

### test_evaluation.py

[Source](https://github.com/McDermottHealthAI/meds-algorithm/blob/main/tests/test_evaluation.py)

| Test | What it checks | Why it exists |
|---|---|---|
| `test_every_prediction_shard_is_validated_and_duplicate_keys_fail` | Checks predictions spread across shards, including repeated keys. | Avoid partial validation and duplicate scoring rows. |
| `test_truth_join_selects_each_split_and_preserves_scores` | Attaches split-specific truth to keyed predictions and checks probabilities. | Evaluation enrichment must not change the algorithm's scores. |
| `test_mixed_missing_or_duplicated_labels_fail` | Exercises malformed or incomplete label collections. | Reject ambiguous truth attachment rather than guessing a join. |
| `test_context_cannot_overlap_evaluated_keys_under_another_split_name` | Reuses evaluated keys under a different context split name. | Enforce isolation by actual keys, not just filenames. |
| `test_context_checks_actual_separate_evaluation_index` | Supplies a separate evaluation index with overlapping context examples. | Check the real evaluated cohort even when labels and index have different roots. |
| `test_decoded_rejects_invalid_probabilities` | Parametrizes invalid probability values at output validation. | Prevent invalid scores from reaching evaluation. |
| `test_conformance_never_broadens_missing_splits` | Requests a missing split through conformance helpers. | Do not silently use unrelated rows to make acceptance checks pass. |

### test_integrations.py

[Source](https://github.com/McDermottHealthAI/meds-algorithm/blob/main/tests/test_integrations.py)

| Test | What it checks | Why it exists |
|---|---|---|
| `test_directory_does_not_opt_in_to_provisioning` | Provides a MEDS-DEV checkout under marker expressions that do not opt in. | A configured directory alone must not trigger integration provisioning or downloads. |
| `test_registration_is_per_profile_and_rejects_escape` | Registers distinct profiles and rejects names escaping the destination. | Keep descriptor registrations separate and confined to the intended directory. |
| `test_registration_writes_an_unquoted_editable_file_url` | Checks the editable local-repository URL written into MEDS-DEV configuration. | Produce an installable dependency specification without shell quoting embedded in YAML. |

### test_predicates.py

[Source](https://github.com/McDermottHealthAI/meds-algorithm/blob/main/tests/test_predicates.py)

| Test | What it checks | Why it exists |
|---|---|---|
| `test_resolved_features_are_saved_and_do_not_change_task_predicates` | Merges feature additions, checks saved provenance, and retains the original task predicate binding. | Keep algorithm features auditable without silently changing evaluation semantics. |
| `test_invalid_extensions_never_call_algorithm_or_publish` | Parametrizes duplicate keys/names and malformed additional predicates. | Reject ambiguous feature definitions before work or publication begins. |
| `test_additions_without_base_and_required_config_fields` | Uses only additional predicates with an algorithm config that has required fields. | Support optional base predicates and concrete configuration constructors without hidden defaults. |
| `test_predicate_change_changes_digest_and_modified_resolution_rolls_back` | Changes predicate contents, then makes an algorithm modify the resolved copy. | Record semantic input changes and protect runner-owned predicate provenance. |

### test_process.py

[Source](https://github.com/McDermottHealthAI/meds-algorithm/blob/main/tests/test_process.py)

| Test | What it checks | Why it exists |
|---|---|---|
| `test_run_preserves_output_and_failure` | Checks subprocess output and nonzero-exit propagation. | Do not swallow executable failures or lose diagnostic output. |
| `test_timeout_stops_descendant_work` | Times out a subprocess tree and checks that its descendant cannot finish delayed work. | Prevent abandoned computation after the caller reports a timeout. |

### test_reports.py

[Source](https://github.com/McDermottHealthAI/meds-algorithm/blob/main/tests/test_reports.py)

| Test | What it checks | Why it exists |
|---|---|---|
| `test_unfinished_profile_does_not_hide_completed_evidence` | Checks reports with both completed and stub profiles. | Do not let an unfinished profile exempt a completed profile from its evidence requirements. |
| `test_completing_last_profile_requires_its_evidence` | Marks the last stub complete without supplying its report evidence. | Keep completion gates meaningful for every implemented profile. |

## Installed-wheel verification

`tests/wheel_smoke.py` is a standalone script, not a pytest test. In an environment containing only the
base wheel it checks that optional Polars/pytest dependencies are absent, the contract/UML/test catalogue
are packaged, neural configuration round-trips, artifact publication works with unknown checkout provenance,
and the three installed helper commands accept `--help`. This catches packaging and optional-import
failures that tests run from an editable source checkout can miss.

Run it after `uv build` in a separate environment containing the built wheel and only its base dependencies.
The release workflow also validates distribution metadata with Twine. The full suite can then be rerun
against the installed wheel with its conformance extra and tests copied outside the checkout.

## Maintaining this catalogue

When adding, renaming or changing a test, update its row in this file. Keep the reason distinct from the
assertion: explain the scientific, reproducibility or operational failure the test guards against.
The template docs render this packaged file; do not maintain a second copy of the shared test inventory.
