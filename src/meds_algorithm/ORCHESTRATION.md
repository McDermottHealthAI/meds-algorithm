## Profile runner (prototype)

The optional `meds-algorithm[orchestration]` extra provides one run configuration for local execution
or dependent SLURM jobs. This is a reviewable prototype: existing per-step commands and the shell
launcher remain available. No algorithm methods or request/artifact contracts change.

Dry-run can inspect a stub repository; actual execution requires implemented algorithm methods.
In a generated algorithm repository, install the extra and edit `configs/runs/run.yaml`:

```bash
uv sync --extra orchestration --extra test
uv run my-algorithm run --config-name run --dry-run
uv run my-algorithm run --config-name run execution=local
```

Replace `my-algorithm` with your algorithm's executable. Commands run from the generated repository;
`--config-dir /absolute/path/configs` selects another configuration directory. For a Python integration,
use `RunPlanner`, then `RunCoordinator`; the template's CLI delegates to their shared implementation.

### Supply external inputs once

For example, `configs/runs/mortality.yaml` could contain:

```yaml
defaults:
  - meds_run
  - _self_

profile: supervised
execution: local
output_dir: /runs/mortality-baseline-001
inputs:
  meds_dir: /datasets/mimic/meds
  labels_dir: /tasks/mortality/labels
  index_dir: /tasks/mortality/index
  evaluation_labels_dir: /tasks/mortality/labels
prediction_splits: [held_out]
algorithm: {}  # Concrete AlgorithmConfig defaults; add only actual algorithm fields.
```

The `meds_run` schema is registered by core, so generated YAML does not copy all shared defaults.
Hydra composes YAML defaults/groups, interpolations and CLI overrides. The algorithm's own
`config_type.from_dict` validates the resolved `algorithm` values and fills its defaults. Required
algorithm fields must be provided; unknown fields fail. Frozen/nested algorithm configs remain authoritative.
For an NNConfig implementation, for example, add its learning rate and batch size to `algorithm` in
YAML, then override an existing setting with `algorithm.learning_rate=0.0003`. Hydra requires `+` to
add a key absent from YAML, e.g. `+algorithm.capacity=2`; core still validates the field and value.

All relative input/output and algorithm-config paths resolve against the **invocation working
directory**, including values loaded from YAML. The coordinator does not change that directory or
guess paths relative to included config files. The dry run shows the absolute paths.

### How step arguments are obtained

For a supervised run, the planner derives these connections from the existing typed request specs:

| Stage | External inputs | Artifact connections |
|---|---|---|
| `preprocess_data` | `inputs.meds_dir`, optional `inputs.predicates_file` | Publishes `<output_dir>/artifacts/data`. |
| `train_supervised` | `inputs.labels_dir` | Reads prepared data; publishes `artifacts/supervised_algorithm`. |
| `predict_supervised` | `inputs.index_dir`, `prediction_splits`, optional evaluation labels | Reads data and fitted algorithm; publishes `artifacts/predictions`. |

All six profiles use this derivation. Only stage-specific external-input rules are added:

- Probe embeddings use `embedding_splits` (default `train,tuning,held_out`) and
  `inputs.embedding_index_dir` when supplied, otherwise `inputs.index_dir`. Supply the former when
  training/tuning keys are separate from the evaluated index. Prediction uses `prediction_splits`.
- Zero-shot prediction requires `inputs.task_criteria_file`. It receives `inputs.task_predicates_file`
  when supplied, otherwise the dataset predicates. Preprocessing receives only dataset predicates;
  trajectory inference receives no task criteria or labels.
- Predict-only context is explicit: `inputs.context_labels_dir` and `inputs.context_splits` select
  permitted train/tuning examples. Optional task criteria/predicates are supported.
- `inputs.evaluation_labels_dir` is passed only to final prediction for post-score truth attachment.
- `seed` defaults to zero and is included in every typed request. There is no implicit overwrite.

### Review before executing

```bash
uv run my-algorithm run --config-name mortality --dry-run
uv run my-algorithm run --config-name mortality execution=slurm --dry-run
```

Both print JSON containing the fully resolved configuration, concrete algorithm defaults, absolute
paths, every stage's argument dictionary and exact subprocess `argv`, stage dependencies, resource
requests and Git provenance. Neither creates run/log directories, executes algorithm methods, nor
contacts a scheduler. Input files and reused artifact manifests must exist; produced artifacts need not.
The planner validates argument types, required inputs, artifact envelope types, resource fields and
path overlap. Dataset contents, payload compatibility and scientific behavior are checked by the
existing runner/algorithm during execution, not proven by a dry run.

### Local and SLURM execution

```bash
uv run my-algorithm run --config-name mortality execution=local
uv run my-algorithm run --config-name mortality execution=slurm \
  output_dir=/runs/mortality-slurm-001 \
  resources.cpu.partition=cpu \
  resources.compute.partition=gpu resources.compute.gpus_per_node=1 \
  resources.compute.timeout_min=240
```

Local execution runs stages sequentially in fresh subprocesses and stops at the first failure.
Stage timeout limits apply locally too. CPU, GPU and memory allocation requests are SLURM settings;
local execution does not reserve or isolate those resources. Output streams go directly to per-stage
log files instead of accumulating training logs in the coordinator's memory.

SLURM execution uses Submitit directly to submit one job per stage, chained with `afterok` dependencies.
It returns after submission. A clean committed algorithm checkout is required; workers check that
the commit remains unchanged and the checkout remains clean before starting. Put outputs outside the
checkout or in a Git-ignored directory. Use a shared filesystem and the same installed Python
environment on the submitting and compute hosts. The coordinator does not install environments or
snapshot the source tree. Avoid editing the checkout while jobs are queued/running.

Preprocessing uses `resources.cpu`; other stages use `resources.compute`. Both default to 4 CPUs,
16 GiB memory, 60 minutes and **zero GPUs**. Set resources appropriate to the actual algorithm.
Override individual stages using `resources.steps`, for example in YAML:

```yaml
resources:
  compute:
    gpus_per_node: 1
    timeout_min: 240
  steps:
    predict_supervised:
      mem_gb: 32
```

Supported resource fields are `timeout_min`, `cpus_per_task`, `mem_gb`, `gpus_per_node`, `partition`,
`account` and `qos`. Stage overrides merge with their CPU/compute preset. The prototype supports one
node and one task per stage. Multi-node training, checkpoint/resume, sweeps and automatic retries are
not implemented. It uses Hydra's Compose API, so `--multirun` and `hydra/launcher=submitit_slurm` are
not supported here: `execution=slurm` selects the dependency-aware coordinator. This deliberately
avoids Hydra creating output directories before `--dry-run` has been evaluated.

### Reuse artifacts explicitly

`stages` selects a subset; execution always follows profile order. An omitted producer requires an
explicit existing artifact using its standard input argument name:

```yaml
stages: [train_supervised, predict_supervised]
artifacts:
  input_data_dir: /runs/shared/artifacts/data
```

The existing artifact must have the expected manifest type. Conflicting produced/reused inputs,
unknown/unused overrides, missing inputs and existing output directories fail before execution.
The typed runner continues to enforce algorithm/configuration compatibility when consuming artifacts.
Use a new output directory for every attempt; this prototype does not silently resume partial runs.

### Recorded evidence

Each run saves `plan.json`, the typed `algorithm.json` envelope, and `logs/<stage>.log`.
Every stage receives that exact configuration file; workers detect changes to it before execution.
The existing runner saves `config.json`, `request.json` and `manifest.yaml` inside each published
artifact, including resolved algorithm settings, input identities, seed and resource measurements.
Scheduling settings are in `plan.json`; they do not alter algorithm-compatibility digests.

SLURM additionally writes Submitit's logs and a `submission.json` receipt with stage/job IDs.
If submission fails partway through, the coordinator attempts to cancel already submitted jobs and
records cancellation errors. `submitted` means accepted by the scheduler, not completed successfully.
Monitor job IDs with the cluster's normal tools and inspect artifacts/logs before claiming success.
Local failure leaves its plan, logs and any completed artifacts for inspection.
