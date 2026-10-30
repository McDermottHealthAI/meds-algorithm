# meds-algorithm

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![PyPI: unreleased](https://img.shields.io/badge/PyPI-unreleased-lightgrey)](https://github.com/McDermottHealthAI/meds-algorithm/blob/main/RELEASING.md)
[![Tests and code quality](https://github.com/McDermottHealthAI/meds-algorithm/actions/workflows/ci.yml/badge.svg)](https://github.com/McDermottHealthAI/meds-algorithm/actions/workflows/ci.yml)
[![Documentation](https://img.shields.io/badge/docs-architecture-blue)](https://github.com/McDermottHealthAI/meds-algorithm/blob/main/ARCHITECTURE.md)
[![Contributors](https://img.shields.io/github/contributors/McDermottHealthAI/meds-algorithm)](https://github.com/McDermottHealthAI/meds-algorithm/graphs/contributors)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](https://github.com/McDermottHealthAI/meds-algorithm/pulls)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](https://github.com/McDermottHealthAI/meds-algorithm/blob/main/LICENSE)

Shared infrastructure for implementing and validating MEDS algorithm repositories. The package defines
algorithm profiles and command contracts, manages artifacts and run provenance, reads prediction indices
and training targets, validates prediction outputs, and provides reusable conformance tests.

Algorithm repositories import these utilities so fixes can be distributed through a package update.
Algorithm architectures, tokenizers, training objectives and task-specific logic stay in the algorithm repository.

See the [architecture and UML diagrams](https://github.com/McDermottHealthAI/meds-algorithm/blob/main/ARCHITECTURE.md) for the profile hierarchy, typed requests,
algorithm-owned configuration, artifact references and shared execution path.

## Package layout

```text
src/meds_algorithm/
├── CONTRACT.md                 # canonical normative specification, included in the wheel
├── spec.py                     # installed specification reader
├── algorithms.py               # Algorithm and profile ABCs, lifecycle order
├── requests.py                 # frozen per-step requests and CLI field mappings
├── configuration.py            # AlgorithmConfig, NNConfig and execution options
├── serialization.py            # strict, versioned config/request JSON serialization
├── runner.py                   # validate, execute, measure, publish; CLI adapter
├── contracts/commands.py       # derived compatibility views and legacy dispatch
├── artifacts/
│   ├── references.py           # lazy typed artifact references and payload metadata
│   ├── manifest.py             # measured artifacts, envelope reading and digests
│   ├── publication.py          # unique staging, exclusive writers and overwrite rollback
│   ├── inputs.py               # resolve recorded upstream artifact paths
│   └── results.py              # structured run evidence
├── runtime/
│   ├── provenance.py           # explicitly supplied algorithm checkout
│   ├── resources.py            # process-tree memory sampling and platform fallback
│   └── process.py              # bounded subprocess execution
├── data/                       # split selection, key-only index reads, context targets
├── tasks/spec.py               # TaskSpec and RelaxationLedger
├── evaluation/predictions.py   # keyed probabilities and post-score truth attachment
├── integrations/meds_dev.py    # per-profile registration and CLI
└── conformance/                # assertions, synthetic fixtures, full-lifecycle checks,
                               # opt-in MEDS-DEV provisioning and algorithm adapter result types
```

## Installation and dependencies

Install a reviewed revision with
`pip install 'meds-algorithm @ git+https://github.com/McDermottHealthAI/meds-algorithm.git@<full-commit-sha>'`.
The template currently records the exact SHA. For package-index release checks and publishing setup,
see the [release guide](https://github.com/McDermottHealthAI/meds-algorithm/blob/main/RELEASING.md).

- Base package: PyYAML; no dataframe engine, test runner, GPU or algorithm framework is imported by base APIs.
- `data` extra: Polars for index/target reads and prediction validation.
- `conformance` extra: pytest, Polars, PyArrow and the pinned MEDS evaluation schema implementation.
- `test` extra: dependencies for developing and testing this package.

The installed CLI provides `meds-algorithm-spec`, `meds-algorithm-resolve-input`, and
`meds-algorithm-add-to-meds-dev`. Algorithm repositories provide their own `meds-algorithm` entry point.

New algorithm repositories implement `Algorithm` profile subclasses, receive frozen typed requests, and
execute through `AlgorithmRepository`/`StepRunner`. Their own frozen `AlgorithmConfig` subclass defines
hyperparameters, defaults and validation. Use `config_file=...` for a JSON/YAML values mapping or a
previously saved `config.json`. Typed prediction execution requires the `data` extra. See the
[architecture guide](https://github.com/McDermottHealthAI/meds-algorithm/blob/main/ARCHITECTURE.md) for the complete ownership and serialization algorithm.

Neural algorithms can extend `NNConfig` for a capacity multiplier, learning rate, batch size,
weight decay and dropout. Concrete algorithms define the multiplier-to-architecture mapping and training
defaults. See [neural configuration and scaling](https://github.com/McDermottHealthAI/meds-algorithm/blob/main/ARCHITECTURE.md#neural-network-configuration-and-scaling-experiments)
for an extensible example and the recommended upstream ownership of data scaling.

## Ownership

The template imports this package directly; it does not generate a `meds_algorithm_contract` package or
copy these implementations. Generated files contain algorithm command skeletons, selected profile YAMLs,
execution adapters in `tests/e2e.py`, algorithm-specific tests, and project/cluster configuration.
Family sharing belongs inside one algorithm-family repository with several profiles. Tokenizers,
architectures, objectives, payload layouts and task translators remain algorithm-owned.

`CONTRACT.md` is the only normative document. Template documentation renders it from the installed
package. Algorithm `SPEC.md` files point to it; algorithm implementation reports record local decisions.

MEDS-DEV's upstream interface still uses `model.yaml`, `src/MEDS_DEV/models`, `meds-dev-model`,
`model=`, and `{model_initialization_dir}`. Registration translates the local `algorithms/<profile>/`
layout into that interface; these upstream names are not part of this package's rename.

## Publication, provenance and measurement

Pass the algorithm checkout explicitly to `StepRunner(repo=algorithm_root)` or, for legacy implementations,
`measured_artifact(..., repo=algorithm_root)`. The package never
infers the algorithm from its own installation path or the working directory. Without a supplied checkout,
commit and dirty state are unknown (`null`); wheel deployments must retain algorithm build provenance
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
values as `null`. GPU instrumentation remains the algorithm/framework's responsibility.

## Validation

```bash
uv sync --extra test --group dev
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv build
```

Tests inject publication/restoration failures, launch a child from a worker thread, check explicit
algorithm provenance, reject missing/mixed/overlapping label inputs, and exercise all six lifecycles with
synthetic command implementations. Full-lifecycle conformance reruns algorithm adapters with forbidden
outcomes removed and fresh artifacts; algorithm-specific cutoff, frozen-weight, compatibility and primary
behavior tests remain required. Package tests do not establish scientific validity of a downstream algorithm.

MEDS-DEV provisioning requires explicit `-m meds_dev` or `-m real_data` selection; setting
`MEDS_DEV_DIR` only supplies a source checkout. Unit tests do not download a real dataset or launch
training. Keep each algorithm's data-access and cluster approval rules in its own repository.

## Changes

### 0.4.0a4

- Rename the repository/distribution from `meds-algorithm-core` to `meds-algorithm`, the Python package
  from `meds_algorithm_core` to `meds_algorithm`, and the contract command to `meds-algorithm-spec`.
  Update imports and dependency pins together. No old-name aliases are installed; serialized envelopes
  with old package-qualified type names require an explicit migration before loading.

### 0.4.0a3

- Add optional `NNConfig(AlgorithmConfig)` with a scalar capacity multiplier and strict immutable settings,
  inherited serialization, validation and runner provenance, without neural-framework dependencies.
- Document capacity semantics, configuration sweeps and the distinction between implemented configuration
  and future upstream data-scaling/consumption-reporting integrations.

### 0.4.0a2

- Add optional `AlgorithmConfig.additional_predicates_file` for dataset-specific feature predicates.
  Preprocessing composes it with the base, rejects duplicate names/keys, preserves the resolved file
  and source digests, and keeps task predicates unchanged. Later steps do not reopen temporary sources.

### 0.4.0a1

- Add profile ABCs, typed requests/artifact references and a shared runner that owns validation,
  measured publication and post-score truth attachment.
- Add strict immutable algorithm-owned configuration and versioned config/request serialization; record
  complete resolved values, upstream manifest identities and key-only index identities.
- Derive profile/step metadata from the new classes. Rename the package, Python API, CLI and artifact
  types/arguments to algorithm terminology under contract version 4. No old-name aliases are installed;
  migrations remain separate. Mapping-based execution is available as `LegacyAlgorithmRepository`.
- Include the canonical API/UML architecture guide in the wheel for downstream documentation.

### 0.3.0a3

- Compare seeded full-lifecycle predictions with and without forbidden labels, preserving separate
  training, index and evaluation inputs.
- Validate original and rerun probabilities across every prediction shard, and accept a separate
  evaluation index when checking context-label overlap.
- Terminate subprocess trees on timeout or interruption; deliberately detached services are unsupported.

### 0.3.0a2

- Complete the extraction of shared artifact, runtime, data, task, evaluation, MEDS-DEV and
  conformance utilities from the template; replace the reserved placeholder modules with implementations.
- Add exclusive artifact writers, overwrite rollback, explicit algorithm-checkout provenance and
  process-tree memory sampling with platform fallbacks.
- Reject ambiguous splits, overlapping context/evaluation keys, invalid probabilities and malformed
  artifact manifests; rerun complete profile lifecycles to check for outcome-label leakage.
- Make the core package the source of the contract and shared tests, removing generated copies from
  the template. Migration of existing algorithm repositories is separate.

### 0.3.0a1

- Introduce contract version 3, profile/command definitions, the installed specification reader and
  a key-only prediction index reader.
