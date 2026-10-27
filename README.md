# meds-model-core

Shared infrastructure for implementing and validating MEDS model repositories. The package defines
model profiles and command contracts, manages artifacts and run provenance, reads prediction indices
and training targets, validates prediction outputs, and provides reusable conformance tests.

Model repositories import these utilities so fixes can be distributed through a package update.
Model architectures, tokenizers, training objectives and task-specific logic stay in the model repository.

See the [architecture and UML diagrams](ARCHITECTURE.md) for the current class structure, command
execution, package dependencies, and the tradeoffs around an `Algorithm` superclass and step interfaces.

## Package layout

```text
src/meds_model_core/
├── CONTRACT.md                 # canonical normative specification, included in the wheel
├── spec.py                     # installed specification reader
├── contracts/commands.py       # profiles, command classes, step metadata, dispatch
├── artifacts/
│   ├── manifest.py             # measured artifacts, envelope reading and digests
│   ├── publication.py          # unique staging, exclusive writers and overwrite rollback
│   ├── inputs.py               # resolve recorded upstream artifact paths
│   └── results.py              # structured run evidence
├── runtime/
│   ├── provenance.py           # explicitly supplied model checkout
│   ├── resources.py            # process-tree memory sampling and platform fallback
│   └── process.py              # bounded subprocess execution
├── data/                       # split selection, key-only index reads, context targets
├── tasks/spec.py               # TaskSpec and RelaxationLedger
├── evaluation/predictions.py   # keyed probabilities and post-score truth attachment
├── integrations/meds_dev.py    # per-profile registration and CLI
└── conformance/                # assertions, synthetic fixtures, full-lifecycle checks,
                               # opt-in MEDS-DEV provisioning and model adapter result types
```

## Installation and dependencies

Install a reviewed revision with
`pip install 'meds-model-core @ git+https://github.com/florian6973/meds-model-core.git@<full-commit-sha>'`.
The template currently records the exact SHA. For package-index release checks and publishing setup,
see the [release guide](https://github.com/florian6973/meds-model-core/blob/main/RELEASING.md).

- Base package: PyYAML; no dataframe engine, test runner, GPU or model framework is imported by base APIs.
- `data` extra: Polars for index/target reads and prediction validation.
- `conformance` extra: pytest, Polars, PyArrow and the pinned MEDS evaluation schema implementation.
- `test` extra: dependencies for developing and testing this package.

The installed CLI provides `meds-model-core-spec`, `meds-model-resolve-input`, and
`meds-model-add-to-meds-dev`. Model repositories provide their own `meds-model` entry point.

## Ownership

The template imports this package directly; it does not generate a `meds_model_contract` package or
copy these implementations. Generated files contain model command skeletons, selected profile YAMLs,
execution adapters in `tests/e2e.py`, model-specific tests, and project/cluster configuration.
Family sharing belongs inside one model-family repository with several profiles. Tokenizers,
architectures, objectives, payload layouts and task translators remain model-owned.

`CONTRACT.md` is the only normative document. Template documentation renders it from the installed
package. Model `SPEC.md` files point to it; model implementation reports record local decisions.

## Publication, provenance and measurement

Pass the model checkout explicitly to `measured_artifact(..., repo=model_root)`. The package never
infers the model from its own installation path or the working directory. Without a supplied checkout,
commit and dirty state are unknown (`null`); wheel deployments must retain model build provenance
separately rather than inventing a checkout revision.

Publication uses a unique sibling staging directory and an exclusive destination lock. A new artifact
appears in one rename. Overwrite retains the old directory as a backup until the new directory is
published, and restores it if publication fails. Replacement uses two renames, so concurrent readers
can briefly observe an absent destination. Prefer immutable output paths for concurrent readers.
This is not a power-loss transaction: after a process crash, inspect the `.lock`, `.staging-*` and
`.backup-*` siblings before manually recovering. If restoration itself fails, the exception names the
preserved backup; it is never silently deleted. Locks apply to cooperating core writers.

Linux sampling visits the children of every process thread, including subprocesses launched by worker
threads. Sampling can miss short-lived peaks; inaccessible descendants are not a complete measurement.
On platforms without `/proc`, use process-only `getrusage` when available; otherwise report unavailable
values as `null`. GPU instrumentation remains the model/framework's responsibility.

## Validation

```bash
uv sync --extra test --group dev
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv build
```

Tests inject publication/restoration failures, launch a child from a worker thread, check explicit
model provenance, reject missing/mixed/overlapping label inputs, and exercise all six lifecycles with
synthetic command implementations. Full-lifecycle conformance reruns model adapters with forbidden
outcomes removed and fresh artifacts; model-specific cutoff, frozen-weight, compatibility and primary
behavior tests remain required. Package tests do not establish scientific validity of a downstream model.

MEDS-DEV provisioning requires explicit `-m meds_dev` or `-m real_data` selection; setting
`MEDS_DEV_DIR` only supplies a source checkout. Unit tests do not download a real dataset or launch
training. Keep each model's data-access and cluster approval rules in its own repository.

## Changes

### 0.3.0a3

- Compare seeded full-lifecycle predictions with and without forbidden labels, preserving separate
  training, index and evaluation inputs.
- Validate original and rerun probabilities across every prediction shard, and accept a separate
  evaluation index when checking context-label overlap.
- Terminate subprocess trees on timeout or interruption; deliberately detached services are unsupported.

### 0.3.0a2

- Complete the extraction of shared artifact, runtime, data, task, evaluation, MEDS-DEV and
  conformance utilities from the template; replace the reserved placeholder modules with implementations.
- Add exclusive artifact writers, overwrite rollback, explicit model-checkout provenance and
  process-tree memory sampling with platform fallbacks.
- Reject ambiguous splits, overlapping context/evaluation keys, invalid probabilities and malformed
  artifact manifests; rerun complete profile lifecycles to check for outcome-label leakage.
- Make the core package the source of the contract and shared tests, removing generated copies from
  the template. Migration of existing model repositories is separate.

### 0.3.0a1

- Introduce contract version 3, profile/command definitions, the installed specification reader and
  a key-only prediction index reader.
