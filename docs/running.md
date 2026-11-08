# Running an algorithm

A generated repository exposes one command-line entry point, a MEDS-DEV descriptor, and a SLURM
interface. All three run the same commands with the same standard arguments.

For a copyable sequence from an empty directory to verified predictions, start with the
[fully manual example](manual-example.md). It includes setup, implementation code and synthetic inputs.

<!-- orchestration-guide -->

## Individual step commands

Run these commands from the generated repository after `uv sync --extra test`. The examples assume
`algorithm_slug: my_algorithm`, which installs the command `my-algorithm`; replace it with your own
algorithm's command (the slug with underscores changed to hyphens).

Pass `config_file=/absolute/path/dataset_configs/mimic_iv.yaml` to each lifecycle invocation to select
algorithm settings, including optional `additional_predicates_file`. See [feature additions](concepts.md#additional-feature-predicates-per-dataset).
For MEDS-DEV, add the same `config_file=...` argument to each command in the selected descriptor; use a
path accessible inside its execution environment. MEDS-DEV still supplies the base `{predicates_path}`.
For SLURM, set `ALGORITHM_CONFIG_FILE` to an absolute configuration path; generated `stage_args` passes
it to every selected step. No dataset is inferred from a directory name, and no upstream file is edited.

```bash
uv run my-algorithm profiles
uv run my-algorithm commands --profile zero_shot_direct
uv run my-algorithm predict_zero_shot_direct --profile zero_shot_direct \
  input_data_dir=runs/x/data input_pretrained_algorithm_dir=runs/x/pretrained \
  external_index_dir=/task/index external_task_criteria_file=/task/criteria.yaml \
  splits=[held_out] output_predictions_dir=runs/x/predictions
```

Multiple profiles require explicit selection; a single-profile repository may omit `--profile`.
Arguments are `key=value`; booleans and numeric values are decoded, and `splits=[train,tuning]` is a list.
Inference and prediction require a nonempty explicit split list. Additional algorithm settings must be
validated and included in the resolved configuration digest. See the
[per-step argument table](reference/spec.md#9-software-interfaces).

Scoring and inference take `external_index_dir` (keys only). Training and optional in-context examples
use `external_labels_dir`. `external_evaluation_labels_dir` is optional and only attaches outcomes after
scores are fixed. The two directories may physically share files; their reader roles remain separate.

Supervised/fine-tuned prediction requires `input_data_dir`; probe prediction requires
`input_embeddings_dir`. MEDS-DEV resolves recorded upstream paths into explicit CLI arguments with
`meds-algorithm-resolve-input`; SLURM passes the chosen artifact paths directly.

## MEDS-DEV

`algorithms/<profile>/model.yaml` is the [MEDS-DEV](https://github.com/Medical-Event-Data-Standard/MEDS-DEV) descriptor. Its
`unsupervised` / `supervised` × `train` / `predict` slots hold command strings with these template
variables:

| Variable | Filled by MEDS-DEV with |
|---|---|
| `{dataset_dir}` | the MEDS dataset |
| `{labels_dir}` | the task's labels (the index) |
| `{output_dir}` | this stage's output directory |
| `{model_initialization_dir}` | the previous stage's `{output_dir}` |
| `{split}` | the split to predict (`held_out` in full mode) |
| `{predicates_path}` | the dataset's predicates file (`predicates_path` argument; MEDS-DEV PR #325) |
| `{task_criteria_path}` | the task's ACES criteria: the `task_criteria_path` argument, else the registered criteria file of `task_name` (MEDS-DEV PR #330) |

Every artifact gets its own subdirectory of the MEDS-DEV run directory: `data/`, `pretrained/`, `algorithm/`,
`embeddings/` or `trajectories/`, `predictions/`. Nothing is written to `{output_dir}` itself, because MEDS-DEV keeps its own
`cmd.sh` and `.done` marker there and artifacts are published by publishing their destination
directory. Artifacts are never nested inside one another, so runs over different indexes or splits cannot
overwrite each other's outputs.

MEDS-DEV evaluates every `**/*.parquet` under the predictions directory with meds-evaluation 0.0.3, so
every parquet file there must be a predictions file (see the [FAQ](faq.md)).

Register a completed repository with MEDS-DEV by copying its descriptor into a MEDS-DEV checkout:

```bash
uv run meds-algorithm-add-to-meds-dev --meds-dev /path/to/MEDS-DEV --name my_algorithm --profile probe
```

This registers `algorithms/probe/model.yaml` as `my_algorithm__probe`. Register each desired profile separately.

The `meds_dev` test tier
provisions MEDS-DEV at a pinned commit that supplies both passthroughs (currently the head of PR #330, which
builds on PR #325); set `MEDS_DEV_REF` to use another revision. A checkout supplied through
`MEDS_DEV_DIR` is capability-checked rather than silently used; only zero-shot repositories require
`{task_criteria_path}`.

## SLURM

`slurm/config.sh` is the only SLURM file meant for routine edits: partitions, time limits, CPUs, memory,
GPUs, and `stage_args`, which prints each command's `key=value` arguments from environment variables
(`MEDS_ROOT`, `INDEX_DIR`, `LABELS_DIR`, `TASK_CRITERIA_FILE`, `RUN_DIR`).

```bash
$EDITOR slurm/config.sh
PROFILE=probe ./slurm/submit.sh --dry-run    # prints every sbatch call and each command's arguments; changes nothing
PROFILE=probe ./slurm/submit.sh              # submits the profile as dependent jobs
```

- `stage_args` covers the declared union; submission validates and lists only the selected profile's commands.
- Each command is one job; later commands depend on earlier ones (`afterok`). `preprocess_data` runs on the
  CPU partition, the others on the GPU partition.
- Submission refuses a dirty working tree, so every cluster run corresponds to a commit. `--dry-run` only
  warns, so a run can be reviewed before it is committed.
- Artifacts land under `runs/<run-id>/<profile>/artifacts`.

## Run results and GitHub sync

`write_run_result(..., profile="probe")` assembles a run's structured evidence under `runs/<run-id>/`, and

```bash
scripts/github-sync.sh <run-id>
```

commits exactly these files on a new `runs/<algorithm>/<run-id>` branch, pushes that branch, and opens a draft
PR for it. It changes nothing else.

| Pushed | Contents |
|---|---|
| `runs/<run-id>/spec.yaml` | the dataset (name and counts as given), the task, and the predicates file's path and digest |
| `runs/<run-id>/result.yaml` | status; git commit and dirty state; environment (host, platform, Python, CPU count, SLURM job id); per-command resource summary |
| `runs/<run-id>/manifests/*.yaml` | a copy of every command's `manifest.yaml` |

| Never pushed | Why |
|---|---|
| predictions | they are artifacts under `runs/<run-id>/<profile>/artifacts`, not evidence files |
| labels, datasets | patient data stays where it is |
| checkpoints and other artifact payloads | large and algorithm-owned |
| raw logs, credentials | may contain anything |
| metrics (AUROC, …) | the template computes no metrics; MEDS-DEV's evaluation step (meds-evaluation) does |

If the push fails, the result stays committed locally on the run branch.
