# MEDS Model Repository Contract, version 3 draft

This document is the single authoritative contract shipped with meds-model-core. Model repositories
pin a core version and refer to its contract; they do not maintain copies of these rules. A conforming repository turns a MEDS dataset, an optional task, and an optional semantic
specification into MEDS predictions through one or more of six fixed model profiles. How a command performs its
work is deliberately outside this contract.

## 1. Principles

- The input and final output are interoperable; intermediate payloads are implementation-owned.
- Commands have stable meanings, but do not prescribe Python, batching, tensors, training frameworks,
  checkpoint formats, or execution hardware.
- Every intermediate artifact has a standard manifest envelope even when its payload is opaque.
- A repository is operational: it declares itself through `models/<profile>/model.yaml`, tests its real implementation end
  to end, runs locally or through SLURM, and can exchange structured run results through GitHub.
- The six model profiles are the supported command lifecycles. A repository declares a nonempty set; it does not invent an
  undocumented profile.

## 2. Inputs

### 2.1 MEDS dataset

`external_meds_dir` MUST be a valid, split-sharded MEDS dataset. Event semantics come from the versioned
MEDS standard. Implementations MUST NOT reinterpret `subject_id`, `time`, `code`, value columns, static
events (`time = null`), or code metadata incompatibly. MIMIC-IV demo in MEDS form is the canonical real
data example, not an additional schema.

The `train`, `tuning`, and `held_out` splits are a boundary, not a convention. Any statistic fitted over a
population — vocabularies, code frequencies, quantile bins, normalization constants, feature selections —
MUST be fitted on the training split alone. Fitting one over all splits is *transductive* leakage: it is
not label leakage, because quantities like code frequency are label-independent, so an implementation can
satisfy every label-leakage check while carrying it. Where the fitting scope is not the implementation's
to control, because preprocessing is delegated upstream, it MUST declare which quantity was fitted over
which population rather than leave the scope unstated.

### 2.2 Task

A task input is an index of `(subject_id, prediction_time)` and, for training/evaluation only, a value
column such as `boolean_value`. Labels of an **evaluated split** MUST never be read to produce a
prediction. Which other labels a command may read depends on the profile:

The per-step table in section 9 specifies access to **ground-truth target values**, such as
`boolean_value`. These are different from index keys `(subject_id, prediction_time)` and from the
model's predicted probability. Inference and ordinary scoring receive `external_index_dir` and project
only its keys. Training receives `external_labels_dir`; in-context prediction may also receive that
argument solely for explicitly permitted train/tuning context examples. Zero-shot commands read none.

MEDS-DEV may map its existing `{labels_dir}` source to `external_index_dir`. That is a key-only view of
the same files, not permission to load their outcome columns. A physically separate keys-only index is
also supported. Neither representation rebuilds or filters the upstream cohort.

Once scores are fixed, an evaluation adapter MAY use `external_evaluation_labels_dir` to join truth onto the
predictions by key (`meds_model_contract.attach_ground_truth`), because meds-evaluation reads ground truth
from the predictions file. Nothing computed from that join may feed back into a prediction.

The cohort is built upstream, not in the model repository. The index and its labels come from one
extraction run outside every model: MEDS-DEV's `meds-dev-task` for the MIMIC-IV demo, and a shared, reviewed
task bundle for full-data runs, whose tasks may be clinical tasks defined in ACES or randomly sampled
code-by-horizon tasks. That extraction applies the trigger, inclusion/exclusion criteria, and splits once,
so every model scores the same keys. A model repository
MUST NOT re-extract, filter, or extend the index; it predicts every requested row (section 5). This holds
for zero-shot profiles too: they receive the ACES task (section 2.4) to build their *query*, never to
rebuild their cohort.

### 2.3 Dataset predicates

Dataset-specific predicates are external inputs, supplied through the established
`external_predicates_file` argument. When MEDS-DEV provides predicates for a dataset, the repository MUST
reuse them rather than duplicating dataset knowledge in the model template. In particular, the MIMIC-IV
demo MUST use MEDS-DEV's MIMIC-IV predicates. A model decides whether and how to consume them: token
selection, SQL, columns, time-series extraction, direct event matching, or no use at all are equally valid.
Any command that consumes the file MUST record its digest and origin.

A model that depends on particular predicate names declares and validates those requirements in its own
configuration and tests. The contract does not prescribe a predicate-derived feature representation.

### 2.4 Task specification (zero-shot profiles)

A supervised model learns what to predict from labels. A zero-shot model never sees labels, so the task
definition itself is an input. The task language is [ACES](https://eventstreamaces.readthedocs.io/): a task
is an ACES criteria file, supplied through `external_task_criteria_file`, bound to the dataset predicates of
section 2.3 when the criteria do not define their own. The pair is the *task specification*
(`meds_model_contract.TaskSpec`).

- Every command of a `zero_shot_*` profile whose output depends on the task (`ZERO_SHOT_TASK_COMMANDS`:
  `predict_zero_shot_direct` and `predict_zero_shot_materialized`) MUST receive `external_task_criteria_file`, MUST
  validate it before expensive work, and MUST record `TaskSpec.provenance()` under `inputs.task` and
  `TaskSpec.semantics_digest()` as the manifest `semantics_digest`.
- The predicates bound to the task can define the label itself (a task-suite layer defining, say, `aki`).
  Such a file MUST reach only task-conditioned commands, never a command that builds model inputs:
  `preprocess_data` receives dataset-level predicates only. Through SLURM the two are `PREDICATES_FILE` and
  `TASK_PREDICATES_FILE`. Through MEDS-DEV there is no conflict, because its task YAMLs carry their label
  predicates and `{predicates_path}` holds dataset facts only.
- Those commands receive the task index through `external_index_dir` for its keys only. They MUST read it
  through `meds_model_contract.read_index`, or an equivalent that never selects a label column.
- Through MEDS-DEV, the criteria path reaches `models/<profile>/model.yaml` as `{task_criteria_path}` (MEDS-DEV PR #330):
  the `task_criteria_path` argument, else the registered criteria file of `task_name`. MEDS-DEV forwards
  the original task; relaxing it is the model's job.

`predict_only` MAY accept the same argument as provenance without requiring it. Other non-zero-shot
commands reject it. Only zero-shot prediction commands bind `semantics_digest` to a task.

## 3. Commands and model profiles

A repository registers the union of its declared profiles once. Only `preprocess_data` and `pretrain`
are shared step names. Every other step has a distinct meaning and name. Unsupported steps fail; the
old `infer`, `supervised_train`, and `predict` names are not aliases.

| Profile | Commands in dependency order |
|---|---|
| `supervised` | `preprocess_data → train_supervised → predict_supervised` |
| `finetune` | `preprocess_data → pretrain → train_finetune → predict_finetune` |
| `probe` | `preprocess_data → pretrain → infer_embeddings → train_probe → predict_probe` |
| `zero_shot_direct` | `preprocess_data → pretrain → predict_zero_shot_direct` |
| `zero_shot_materialized` | `preprocess_data → pretrain → infer_trajectories → predict_zero_shot_materialized` |
| `predict_only` | `preprocess_data → predict_only` |

The CLI is `meds-model <step> --profile <profile> key=value ...`. `meds-model profiles` lists declared
profiles; `meds-model commands --profile <profile>` lists their steps in dependency order. Profile
selection is mandatory when more than one is declared, including for shared commands. The dispatcher
MUST reject a step belonging to another profile before invoking any model code.

`predict_only` preserves the former packaged lifecycle: preprocessing followed by prediction, with no
training command. Fixed published models and in-context learners can both use it. In-context examples
MUST come only from explicitly declared train/tuning splits disjoint from evaluated splits; there is no
persistent task-head training hidden in this profile.

The required Python boundary consists of `Command`, `CommandName`, `ArtifactType`, `ArtifactInput`,
`StepSpec`, `STEP_SPECS`, and `ModelRepository`. Their signatures and the detailed per-step software
requirements are specified in section 9 below. Implementations MUST meet
those requirements even when their backend is an external process. Framework internals are model-owned.

### 3.1 Zero-shot prediction

A zero-shot model maps *(task specification, label-blind index, MEDS dataset)* to *predictions* with no
task-specific training. The two zero-shot profiles differ in **how the model answers**, not in how the
code is organized:

| Profile | The model... | Materialization | Prediction | Examples |
|---|---|---|---|---|
| `zero_shot_direct` | answers a query derived from the task directly (a probability, hazard, or score per query) | none | translates the task into the model's queries, runs the model, decodes probabilities | MOTOR (time-to-event hazards), EveryQuery (code-in-window queries) |
| `zero_shot_materialized` | generates (*materializes*) possible futures, and the task is evaluated on them | task-independent: futures at the index's prediction times, reusable across tasks | applies the task to the materialized futures (e.g. ACES over each sampled trajectory) and aggregates | autoregressive EHR generators |

In `zero_shot_materialized`, `infer_trajectories` never receives the task and records `semantics_digest: null`. Its `predict_zero_shot_materialized`
receives `external_meds_dir`, because the task is evaluated on the real history plus each generated future. Its
output serves every task over the same index. Only the prediction step is task-conditioned. A materialized model
can usually evaluate the task exactly, past criteria included, because ACES runs on the real history plus
the generated future. Its ledger then lists only the sampling approximation. A direct model reduces the
task to its query language, and its ledger lists every reduction. Intermediate payloads are
implementation-defined, as in section 4.

**Relaxations.** Most zero-shot models cannot answer an arbitrary ACES task exactly; they answer a related
question their query language can express. Every zero-shot run MUST therefore publish `relaxations.yaml`
(`meds_model_contract.RelaxationLedger`) in a task-conditioned artifact. Three fields are required:

```yaml
query_language: MOTOR first-occurrence time-to-event over task-head codes   # required
decoded_quantity: P(any of {MEDS_DEATH} first occurs before the first of {ICU_DISCHARGE, MEDS_DEATH})  # required
exact: false                                                                # required
steps:                                                                      # free-form, recommended
  - {name: normalize, kind: label_preserving, direction: exact, detail: re-rooted at the prediction time}
  - {name: label_only, kind: model_assumption, direction: unknown, detail: dropped 2 criteria branches}
```

`exact: true` is a claim that the decoded quantity is the requested label's probability under the model;
an exact model lists no steps. Each entry of `steps` describes one rewrite or assumption; its keys are not
validated, and the implementation guide recommends a vocabulary for them. A model MUST raise rather than
answer a task it cannot pose (for example, a direct model given a task whose label is not future-only):
the command fails and writes no predictions. A model MUST NOT omit a step because it is expected to be
small.

## 4. Intermediate artifacts

Every artifact directory MUST contain `manifest.yaml`, written last through atomic publication. Required
envelope fields are:

```yaml
contract_version: "3"
artifact:
  type: patients | pretrained_model | embeddings | trajectories | supervised_model | finetuned_model | probe_model | predictions
  payload_format: implementation-defined/version
  producer: importable-or-external-implementation-id
command:
  name: <one exact CommandName from the selected profile>
  config_digest: sha256:...  # digest_config(arguments + resolved model-owned settings)
code:
  git_commit: <sha> | null   # null outside a git checkout
  dirty: true | false | null # whether the working tree had uncommitted changes
inputs: {}
semantics_digest: null | sha256:...  # TaskSpec digest for task-conditioned artifacts (section 2.4)
resources: {}
```

`config_digest` is `meds_model_contract.digest_config` over the command's arguments plus any model-owned
settings it resolved (defaults, configuration files), so two artifacts made with the same configuration
share it. `code` is recorded automatically by `measured_artifact`: a run from a modified tree is
identifiable as such. Inputs MUST include stable identifiers or digests, including an external predicates
digest when the command consumes one. Consumers MUST reject incompatible artifact type, contract version,
or payload format before doing expensive work.

Each artifact is its own directory, published by atomically replacing that directory. Artifacts MUST NOT
be nested inside one another: `infer_embeddings` writes to `output_embeddings_dir` and `infer_trajectories` to `output_trajectories_dir`, a sibling of the data and
predictions directories, never to a subdirectory of the shared `patients` artifact, so runs over different
indexes or splits cannot overwrite each other. In a MEDS-DEV run directory the layout is `data/`,
`pretrained/`, `model/`, `embeddings/` or `trajectories/`, `predictions/`, next to MEDS-DEV's own files.

## 5. Final predictions

Predictions MUST conform to the prediction schema of the meds-evaluation version MEDS-DEV evaluates with
(currently `meds-evaluation==0.0.3`, `validate_binary_classification_schema`). MEDS-DEV evaluates every
`**/*.parquet` under the predictions directory, so every parquet file in the predictions artifact MUST be a
predictions file; supporting tables (for example a zero-shot query bundle) use another format, such as
Arrow IPC. Predictions MUST contain exactly one
row for every requested `(subject_id, prediction_time)` unless an explicitly declared exclusion policy
permits otherwise. Keys MUST be unique. Row order is not meaningful and MUST never be used to associate
outputs with keys. Extra output columns are permitted only when documented by the selected task/output
kind. Conformance tests MUST compare actual prediction keys directly with the requested evaluation index;
self-reported coverage counts are not proof of coverage. Manifests MAY include coverage counts as diagnostic
metadata. Any exclusion policy MUST identify its excluded keys so tests can validate the resulting index.

Zero-shot predictions are evaluated against the labels of the *requested* task, never the relaxed one: the
relaxation is part of the model. The prediction artifact MUST carry or reference the `relaxations.yaml` that
produced it, so a reader can tell model error from relaxation error.

## 6. Measurements

Every command invocation MUST record measurements, whether run locally, in tests, through MEDS-DEV, or on
SLURM:

```yaml
resources:
  wall_seconds: 1.25
  memory:
    peak_process_tree_pss_bytes: 123456
    peak_process_tree_rss_bytes: 234567
    sampling_interval_seconds: 0.25
    source: linux_proc_smaps_rollup
    includes_descendants: true
  gpu:
    peak_allocated_bytes: null
    peak_reserved_bytes: null
    source: null
  measurement:
    schema_version: "1"
```

Wall time uses a monotonic clock. On Linux, memory is sampled over the live process tree and PSS is the
primary comparison value because it apportions shared pages. RSS is retained as a diagnostic. Scheduler
`MaxRSS`, when available, is a separate value with different semantics. `null` means not measured or not
applicable; zero means measured with no allocation. Manifests MAY also report meaningful work units such
as subjects, events, rows, timepoints, or optimizer steps. Resource values are observations, never
portable pass/fail thresholds.

## 7. Required repository interfaces

- Every declared profile MUST have `models/<profile>/model.yaml`, valid for MEDS-DEV. Its external
  `unsupervised`/`supervised` and `train`/`predict` slots are unchanged; each command selects its profile.
  Registration uses `<model-name>__<profile>` so separate descriptors coexist in MEDS-DEV.
- `tests/test_end_to_end.py` MUST execute each declared profile independently and validate final
  prediction keys, schema, manifests, and resource blocks. A stub MAY skip explicitly during initial
  implementation; a completed port MUST have zero stub skips.
- The model-owned end-to-end adapters MUST identify the labels/evaluation index and evaluated splits so
  generic tests can compare requested and written prediction keys directly. `run_e2e` MUST also return the
  exact `predict` arguments it used, and MUST apply `tests.signal.add_split_canaries` to its fixture and
  return the canaries. `fitted_codes` MUST report every code the model fitted a population statistic for,
  read from its artifacts.
- `meds-model-add-to-meds-dev` (`meds_model_contract.meds_dev.register`) installs `models/<profile>/model.yaml` and
  `requirements.txt`, with the repository as an editable requirement, into a MEDS-DEV checkout. A
  top-level `predicates.yaml` is copied as well when the repository has one. MEDS-DEV's own dataset
  predicates remain the default (section 2.3).
- `slurm/submit.sh --dry-run` MUST print the model-profile submission without mutation. `slurm/submit.sh`
  MUST submit the selected model profile with dependencies, per-stage resources, durable results, and no interactive-shell
  dependency.
- Cluster runs MUST record the exact Git commit, dirty state, environment, machine, scheduler job id, and
  references to command manifests.
- GitHub synchronization MUST use a run branch, never push results directly to the default branch, commit
  structured specifications/results/manifests rather than data, checkpoints, credentials, or raw logs,
  and leave results recoverable on disk if authentication or push fails.
- `tests/test_meds_dev_e2e.py` and `tests/test_mimic_demo_e2e.py` MUST exercise the completed model through
  MEDS-DEV and the MIMIC-IV demo respectively. Both explicitly skip while `STUB_PROFILES` is true. The MIMIC
  test runs the full model profile on MEDS-DEV's `mortality/in_icu/first_24h` task and validates only standard
  boundaries; preprocessing payloads remain opaque.

## 8. Conformance

The generated repository MUST test command discovery, selected-model-profile consistency, artifact compatibility,
atomic publication, predicate provenance, prediction key coverage/uniqueness, absence of label
leakage and of transductive fitting (section 2.1), resource measurement presence, `models/<profile>/model.yaml`, SLURM
dry-run, and its real end-to-end chain. The rendered `tests/test_end_to_end.py` does so in one real run:

- **Label leakage:** `predict` is run again on a copy of the index whose evaluated splits have no label
  column (every split for zero-shot profiles), and MUST still cover every key. Any read of an evaluated
  split's labels fails. `attach_ground_truth` returns predictions unchanged on an unlabelled index.
- **Transductive fitting:** every tuning and held-out subject carries a canary code that occurs in no
  training subject. None of the canaries may appear in `fitted_codes`.
- **Configuration:** every manifest carries a `config_digest`.

A zero-shot repository additionally tests that task-conditioned manifests carry the task's semantics
digest and that a valid `relaxations.yaml` is published.
MIMIC-IV demo conformance is opt-in through a `real_data` pytest marker; a normal test run MUST NOT
download it.

## 9. Software interfaces

### Public classes and ownership

| Symbol | Required behavior |
|---|---|
| `CommandName` | Enumerates the distinct supported steps. No generic `infer`, `supervised_train`, or `predict` aliases. |
| `ArtifactType` | Separates patients, pretrained models, embeddings, trajectories, three kinds of task model, and predictions. |
| `ArtifactInput(argument, artifact_type)` | Describes one required upstream artifact argument and its envelope type. |
| `StepSpec` | Declares `artifact_type`, `output_argument`, `artifact_inputs`, `external_arguments`, `requires_splits`, `label_access`, and `task_conditioned`. Immutable. |
| `STEP_SPECS` | Maps every `CommandName` to its specification. There are no profile-dependent meanings of one step. |
| `Command.run(arguments: Mapping[str, Any]) -> Path` | Model-owned abstract method. Returns the complete published artifact directory or raises. No successful stub or skipped-stage artifact. |
| `Command.__call__(arguments) -> Path` | Validates required path arguments, split-list shape, boolean overwrite and task-argument routing, then invokes `run`. |
| `ModelRepository(profiles: Sequence[str], commands: Mapping[CommandName, type[Command]])` | Requires unique declared profiles and exactly their command union. Registry keys must agree with each class's `name`. |
| `ModelRepository.run(name, arguments, *, profile=None) -> Path` | Selects a declared profile; rejects cross-profile dispatch. Omitting the profile is valid only for a single-profile repository. |
| `TaskSpec`, `RelaxationLedger` | Bind task-conditioned predictions to criteria/predicates and report any semantic approximations. |

`StepSpec.validate` checks the interface shape; it does **not** verify the dataset, label isolation,
upstream content identity, tensor shape, payload format, weights, or scientific correctness. Each
concrete command MUST validate those relevant to its inputs before expensive work. Unknown
model-specific keys are allowed at this boundary, but the concrete command MUST reject misspellings and
invalid values and include resolved defaults in its configuration digest.

Implement the generated `PreprocessData`, `Pretrain`, `TrainSupervised`, `PredictSupervised`,
`TrainFinetune`, `PredictFinetune`, `InferEmbeddings`, `TrainProbe`, `PredictProbe`,
`InferTrajectories`, `PredictZeroShotDirect`, `PredictZeroShotMaterialized`, and `PredictOnly` classes
that belong to the declared profiles. Only one class is registered for each shared step. Helpers inside
those classes are model-owned; no generic tensor or DataLoader interface is imposed.

### Step arguments and artifacts

Every step accepts optional boolean `do_overwrite` (default false). Dataset predicates may be supplied to
preprocessing; task predicates may be supplied to zero-shot prediction. Inference and prediction require
an explicit nonempty `splits` list. `external_index_dir` identifies the upstream keys-only view; `external_labels_dir` supplies permitted
training/context outcomes. Optional `external_evaluation_labels_dir` is evaluation-only, after scoring.

| Step | Required inputs | Output argument → type | Ground-truth target values the model may use |
|---|---|---|---|
| `preprocess_data` | `external_meds_dir` | `output_data_dir` → `patients` | None |
| `pretrain` | `input_data_dir` | `output_pretrained_model_dir` → `pretrained_model` | None |
| `train_supervised` | `input_data_dir`, `external_labels_dir` | `output_supervised_model_dir` → `supervised_model` | Training for fitting; tuning for selection |
| `predict_supervised` | `input_supervised_model_dir`, `input_data_dir`, `external_index_dir`, `splits` | `output_predictions_dir` → `predictions` | None |
| `train_finetune` | `input_data_dir`, `input_pretrained_model_dir`, `external_labels_dir` | `output_finetuned_model_dir` → `finetuned_model` | Training for fitting; tuning for selection |
| `predict_finetune` | `input_finetuned_model_dir`, `input_data_dir`, `external_index_dir`, `splits` | `output_predictions_dir` → `predictions` | None |
| `infer_embeddings` | `input_data_dir`, `input_pretrained_model_dir`, `external_index_dir`, `splits` | `output_embeddings_dir` → `embeddings` | None; read keys only |
| `train_probe` | `input_embeddings_dir`, `external_labels_dir` | `output_probe_model_dir` → `probe_model` | Training for fitting; tuning for selection |
| `predict_probe` | `input_probe_model_dir`, `input_embeddings_dir`, `external_index_dir`, `splits` | `output_predictions_dir` → `predictions` | None |
| `infer_trajectories` | `input_data_dir`, `input_pretrained_model_dir`, `external_index_dir`, `splits` | `output_trajectories_dir` → `trajectories` | None; read keys only |
| `predict_zero_shot_direct` | `input_data_dir`, `input_pretrained_model_dir`, `external_index_dir`, `external_task_criteria_file`, `splits` | `output_predictions_dir` → `predictions` | None |
| `predict_zero_shot_materialized` | `input_data_dir`, `input_trajectories_dir`, `external_meds_dir`, `external_index_dir`, `external_task_criteria_file`, `splits` | `output_predictions_dir` → `predictions` | None |
| `predict_only` | `input_data_dir`, `external_index_dir`, `splits` | `output_predictions_dir` → `predictions` | None for fixed models; explicitly selected disjoint train/tuning context for in-context models |

All prediction commands may attach evaluation truth by key **after** probabilities are final. That
evaluation-only join cannot influence scores, model selection, preprocessing, or query generation.

### Preprocessing and pretraining

`PreprocessData` MUST separate fitting from transformation internally. Fit vocabularies, bins,
normalization and feature selection on training subjects only; freeze them before transforming tuning
or held-out subjects. No task labels or label-defining task predicates are inputs to this shared step.
The artifact records the fitted state, training population identity, code/predicate semantics and
transformation configuration. Transforming a new dataset must reuse that state, not refit it.

`Pretrain` learns a task-independent model from the allowed training population. Self-supervised
targets derived from permitted training histories are allowed; benchmark task labels are not. Tuning
histories may support unsupervised early stopping when explicitly documented. Imported weights are
allowed only as a documented materialization mode with source revision, weight digest and compatibility
checks; this is not a silent no-op. Store everything needed to reconstruct the model.

### Training and prediction bundles

`TrainSupervised` fits the task model from scratch. `TrainFinetune` initializes from the specified
pretrained model and explicitly records which parameters are updated or frozen. `TrainProbe` MUST
leave encoder and preprocessing weights unchanged; only the head and training-fitted head transforms
may change. All three fit on training labels only and use tuning labels for model selection, never
for gradient updates or population statistics.

Task-model artifacts carry fitted weights/head state, preprocessing/code-map identities, output
semantics and upstream provenance. They MUST NOT be assumed to contain the patients or evaluated features.
`PredictSupervised` and `PredictFinetune` explicitly consume `input_data_dir`; `PredictProbe` consumes
`input_embeddings_dir` and its fitted probe. The probe does not rerun an encoder or require a GPU simply
to apply its head. Frozen feature materialization belongs to `InferEmbeddings`.

Every producer records each upstream artifact as `inputs.<argument>.path` plus its content/compatibility
identity. MEDS-DEV's previous-stage-only placeholder can use `meds-model-resolve-input` to resolve that
record into an explicit CLI argument. This checks the envelope type; the consumer must additionally
validate content, feature schema, vocabulary and model identity. Other orchestrators can pass paths
directly. No reliance on current working directories or unrecorded global state is permitted.

### Embeddings and trajectories

`InferEmbeddings` performs frozen inference. Each representation is associated explicitly with
`(subject_id, prediction_time)`; row order cannot establish that association. Record encoder and
preprocessing identities, representation dimension/dtype or opaque schema version, pooling rule and
temporal cutoff convention. Histories must stop at the prediction boundary; boundary inclusion must
match the task protocol. Probe training requires train/tuning coverage; probe prediction requires evaluated-key coverage. The
generated wiring materializes `splits=[train,tuning,held_out]` without reading any label values. Separate
train and evaluation materializations may instead be supplied explicitly, with the same frozen encoder
and feature schema. Set `EMBEDDING_SPLITS` for another requested split set.

`InferTrajectories` generates futures from each requested history without receiving the ACES task.
Record key-to-sample mapping, sample identifiers, seed/sampling policy, generation horizon, time units,
termination/truncation rules, code mapping, and generating-model identity. Reject a later task whose
requested window cannot be answered by the artifact, or explicitly record the approximation; do not
silently treat ungenerated time as event-free. An embedding artifact cannot substitute for trajectories.

### Zero-shot and predict-only

`PredictZeroShotDirect` validates `TaskSpec`, translates the task to supported model queries, runs the
model and decodes one probability per key. Publish the query, decoder settings, task digest and
relaxation ledger. Internal encode/infer/decode methods are not extra CLI stages.

`PredictZeroShotMaterialized` validates task and trajectory coverage, evaluates each requested task on
real history plus the generated futures, and aggregates. Keep the future artifact unchanged. Tasks
with the same key set can reuse it only when horizon and generation semantics also match.

`PredictOnly` is a lifecycle, not a model family: preprocess then predict. Fixed weights/coefficients
must be supplied and identified. In-context learners explicitly declare context selection and can read
only train/tuning labels disjoint from evaluated splits. They do not publish or train a persistent
task-specific model. Optional task criteria may be recorded as provenance.

### Additional compatibility requirements

Before consuming an artifact, check version 3, expected `ArtifactType`, supported `payload_format`,
required files, preprocessing/code-map identity and relevant upstream content digests. For task models,
check task/output identity; for indexed inference, check keys, split selection and temporal cutoff.
Record the checked identities under manifest `inputs`. A filename/size fingerprint is a layout hint,
not a content digest. A configuration hash alone does not establish data or weights identity.

Shared `preprocess_data` and `pretrain` names do not authorize automatic reuse. Profiles with different
tokenization, normalization, populations, model configurations or weights require separate artifacts.
Default SLURM paths include the profile; `SHARED_DIR` is an explicit reuse request that still requires
the same validation. MEDS-DEV descriptors use independent registered model names.

Missing split files, duplicate/conflicting keys, incompatible formats, unsupported tasks and partial
coverage are errors. Failed commands must not publish success manifests. Output directories are
siblings, never nested within an upstream artifact or MEDS-DEV's run-control directory.

### Model-owned internal interfaces

The following is a recommended class decomposition, not a mandatory framework. Document equivalent
responsibilities when the upstream model already has suitable classes:

```python
class Preprocessor:
    def fit(self, training_events, config): ...  # returns immutable fitted state
    def transform(self, events, index, state): ...  # label-blind, cutoff-aware


class FrozenEncoder:
    def encode(self, features, index): ...  # keyed representations, no updates


class TaskTrainer:
    def fit(self, training_features, training_labels, tuning, config): ...
    def save_model(self, fitted, destination): ...  # fitted state and upstream identities


class TaskPredictor:
    def load_bundle(self, source): ...  # validates compatibility first
    def predict(self, prepared_data_or_embeddings, index): ...  # keyed probabilities, never labels


class TrajectoryGenerator:
    def sample(self, histories, index, sampling_config): ...
```

Keep labels out of `transform`, `encode`, `sample`, and ordinary `predict` method signatures.
An in-context predictor should have a separate explicit `context` argument. Any types represented by
ellipses above must be concretely documented in the model repository: key schema, feature schema,
batching ownership, missing-data semantics, save/load compatibility and exception behavior.

### Completion evidence per profile

`PROFILES` and `COMMANDS` declare capability; `STUB_PROFILES` records unfinished implementations.
Acceptance tests are parametrized over every declared profile. Removing one stub flag must not hide
another profile's missing implementation. `run_e2e(tmp_path, *, profile, **inputs)` and
`prepare_meds_dev_run(meds_dev, tmp_path, *, profile)` must honor profile selection and external overrides.

Each completed profile needs full lifecycle, schema/key coverage, manifest/compatibility, temporal
cutoff, train-only preprocessing, primary behavior and negative-control evidence. Probe tests must
verify the encoder remains frozen; finetuning tests must verify the declared update policy; trajectory
tests must verify per-key samples and horizon handling. The template cannot infer these from opaque
payloads. Implement these model-specific assertions rather than relying only on dispatch tests.

The default label-blind prediction rerun checks the prediction path. It does not by itself prove that
earlier artifacts did not cache held-out labels: each implementation must additionally rerun the full
lifecycle with forbidden label columns removed and fresh output directories. Include all external
inputs in `E2EResult.inputs` so that this test can reproduce the same histories and task.
