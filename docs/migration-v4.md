# Migrating to algorithm terminology and typed profiles

Version 4 changes command names, artifact types, descriptor locations and repository dispatch. Do not
reuse version 2 or 3 artifacts by editing their manifest version: validate or rebuild their payloads against
the new contract. The template emits and reads version 4 envelopes.

## From version 3

This is an intentional naming change, with no old-name aliases:

| Previous name | Current name |
|---|---|
| `meds-model-core`, `meds_model_core` | `meds-algorithm`, `meds_algorithm` |
| `ModelConfig`, `MODEL_PROFILES` | `AlgorithmConfig`, `ALGORITHM_PROFILES` |
| `ModelRepository` (mapping-based adapter) | Replace with typed `AlgorithmRepository` |
| `SupervisedModelArtifact` (and pretrained/finetuned/probe equivalents) | `SupervisedAlgorithmArtifact` (and corresponding equivalents) |
| Request field `model` or `algorithm` for fitted prediction state | `fitted_algorithm` |
| `meds-model`, `meds-model-*` helper commands | `meds-algorithm`, `meds-algorithm-*` |
| `input_*_model_dir`, `output_*_model_dir`, `*_model` artifact types | `input_*_algorithm_dir`, `output_*_algorithm_dir`, `*_algorithm` |
| Copier `model_name`, `model_slug`, `model_description` | `algorithm_name`, `algorithm_slug`, `algorithm_description` |
| `commands.py` with `ModelAlgorithm` and generic `Config` | `<slug>.py` with `<AlgorithmClass>` and `<AlgorithmClass>Config` |
| `models/<profile>/model.yaml` | `algorithms/<profile>/model.yaml` |

Set the new `algorithm_class` answer explicitly for acronyms, such as `RETAIN`. Update imports, scripts,
SLURM environment variables (`MEDS_ALGORITHM_*`), lockfiles and persisted invocation descriptions together.
Serialization records concrete class identifiers; old JSON envelopes require an explicit migration.
MEDS-DEV still owns `model.yaml`, its `models/` directory, `meds-dev-model`, `model=`, and
`{model_initialization_dir}`. Those upstream names are intentionally unchanged.

## From older single-profile repositories

1. Replace the Copier `profile` answer with `profiles: [<name>, ...]`. Rename `packaged` to `predict_only`.
   Keep the original source/revision metadata in `.copier-answers.yml` and review the Copier update diff.
2. Implement the selected profile ABCs and associate profiles with concrete classes in `IMPLEMENTATIONS`.
   Shared methods appear once where their semantics match.
3. Rename commands according to the table below. Split previously conditional implementations into
   distinct profile methods, sharing cohesive components where their semantics really match.
4. Update every invocation, manifest producer, output argument, test adapter and SLURM stage selection.
5. Move the MEDS-DEV descriptor to `algorithms/<profile>/model.yaml`; add one for each declared profile.
   Register them independently using `--profile`; the registered name is `<name>__<profile>`.
6. Supply explicit split lists for inference and prediction. Supervised/fine-tuned prediction receives `input_data_dir`; probe prediction receives
   `input_embeddings_dir`. Scoring and inference use `external_index_dir`, not the training-label argument.
7. Replace the global `IS_STUB` boolean with `STUB_PROFILES`. Run the acceptance suite for every profile.
   Record the profile in `write_run_result(..., profile=...)`.

| Profile | Old command | New command |
|---|---|---|
| All | `preprocess_data`, `pretrain` where present | Unchanged |
| supervised | `supervised_train`, `predict` | `train_supervised`, `predict_supervised` |
| finetune | `supervised_train`, `predict` | `train_finetune`, `predict_finetune` |
| probe | `infer`, `supervised_train`, `predict` | `infer_embeddings`, `train_probe`, `predict_probe` |
| zero_shot_direct | `predict` | `predict_zero_shot_direct` |
| zero_shot_materialized | `infer`, `predict` | `infer_trajectories`, `predict_zero_shot_materialized` |
| predict_only (formerly packaged) | `predict` | `predict_only` |

`inference` splits into `embeddings` and `trajectories`, with matching
`input_embeddings_dir`/`output_embeddings_dir` and `input_trajectories_dir`/`output_trajectories_dir`.
Task-algorithm artifacts split into `supervised_algorithm`, `finetuned_algorithm`, and `probe_algorithm`, with matching
input/output argument names. Prediction output remains `output_predictions_dir`.

Use Copier 9.17.1 or newer; the template uses its yield extension to generate a directory for each
selected profile. A single-profile repository may omit CLI `--profile`; a repository with multiple
profiles must select one. There is no ambiguous compatibility alias for the old generic command names.

This revision supplies the interfaces and tests. It does not automatically migrate downstream algorithm
implementations or publish a shared runtime package. See the [package assessment](shared-package-assessment.md).

The core package now owns the single normative `CONTRACT.md`. Generated `SPEC.md` is a pointer to the
installed package version, readable with `meds-algorithm-spec`. The template and generated projects
install the alpha from an immutable Git commit in the separate core repository; no PyPI release is required.

Replace imports from `meds_model_contract` with `meds_algorithm` and remove the generated compatibility
package. Core supplies the registration/input-resolution CLI entry points; keep only the algorithm's own
CLI in its project configuration. Import shared fixtures and checks from `meds_algorithm.conformance`.
For the typed API, pass algorithm provenance explicitly to `AlgorithmRepository(..., repo=algorithm_root)`.
Return `E2EResult` from core's `conformance.types`, recording all external inputs;
the lifecycle checker now reruns every step with forbidden outcomes absent and fresh output paths.
Existing algorithm repositories are not migrated by this template change.

## From mapping-based commands to typed algorithms

Core 0.4.0a5 removes `Command` and `LegacyAlgorithmRepository`. The supported execution path is
`AlgorithmRepository` with typed requests and `StepRunner`. Migrate deliberately:

1. Move command bodies to the selected `Algorithm` profile methods. Use their typed request fields.
2. Put algorithm settings/defaults in a frozen `AlgorithmConfig` subclass; test validation and JSON round trips.
3. Replace internal publication contexts with writes to `request.output.directory` and a returned
   `PayloadMetadata`. Remove algorithm-written manifests and truth attachment; the runner owns those.
4. Extend `validate_inputs` for payload compatibility. Document any override of its default same-algorithm,
   same-config rule, especially for external pretrained artifacts or legacy manifests without config.
5. Route the CLI and end-to-end adapters through `AlgorithmRepository`/`StepRunner`. Verify saved
   requests/configuration and fitted artifacts work in a fresh process.

See [architecture and UML](reference/architecture.md). No private algorithm migration is included here.


## Fitted prediction requests in core 0.4.0a5

`PredictSupervisedRequest`, `PredictFinetuneRequest` and `PredictProbeRequest` now name their saved fitted
artifact `fitted_algorithm`, distinguishing it from the executing Python algorithm instance. Their JSON
schema version is 2; version 1 envelopes are rejected. Reconstruct requests with the current typed API
rather than editing version numbers. External `input_*_algorithm_dir` names are unchanged. Fitted input
manifests must contain the complete resolved config; missing historical fields are no longer filled in.
