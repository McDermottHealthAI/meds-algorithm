# Contract API

The [normative software interfaces](spec.md#9-software-interfaces) define the public classes, arguments,
label-access rules and artifact compatibility requirements. Import them directly from `meds_algorithm`.
There is no generated compatibility package.

| Module | Responsibility |
|---|---|
| `algorithms` | Algorithm/profile ABCs and ordered lifecycles |
| `requests` | Typed per-step inputs and CLI field mappings |
| `configuration`, `serialization` | Algorithm-owned config base, strict versioned JSON round trips |
| `runner` | Shared execution, validation, staging, measurements and publication |
| `contracts.commands` | Derived step specifications and validation |
| `artifacts` | Manifests, publication with rollback, upstream references and run results |
| `runtime` | Explicit algorithm provenance, memory measurement and subprocess execution |
| `data` | Strict split selection, key-only index reads and permitted context targets |
| `tasks.spec` | Task identity and relaxation ledgers |
| `evaluation.predictions` | Keyed probabilities and post-score truth attachment |
| `integrations.meds_dev` | Per-profile registration |
| `conformance` | Reusable assertions, synthetic fixtures and explicitly selected integration tests |

See the [architecture and UML](architecture.md) for profile inheritance and request/artifact types.
Pass the algorithm checkout as `repo=` to `AlgorithmRepository` or `StepRunner`; unavailable provenance is
recorded as null. Algorithm methods return `PayloadMetadata`, while the runner returns a typed published
artifact. Algorithm methods must not bypass the runner or publish artifacts twice.
Use explicit `splits` for outcome attachment. Install the `data` extra for dataframe helpers and the
`conformance` extra for shared tests. The base package does not import data or algorithm frameworks.

`meds-algorithm-spec` prints the installed specification. `meds-algorithm-resolve-input <artifact>
<input_argument>` resolves a recorded upstream path and checks its envelope type; the consumer still
validates scientific compatibility. Core also supplies `meds-algorithm-add-to-meds-dev`.

Algorithm-owned adapters remain `run_e2e(tmp_path, *, profile, **inputs)`, `fitted_codes(artifacts)`, and
`prepare_meds_dev_run(meds_dev, tmp_path, *, profile)`. The shared lifecycle check reruns the selected
profile with evaluated labels removed and fresh outputs; adapters must honor those input overrides,
record and apply the fixture seed, and produce reproducible keyed scores. Use `read_predictions` from
`conformance.assertions` to validate all shards. For separate context/evaluation directories, supply
`evaluation_index_dir` to `read_context_labels`. `conformance.reports.assert_implementation_report`
validates shared evidence and completed profiles independently of unfinished profiles.

`conformance.cases.AlgorithmCase` connects those adapters and representative configurations to
`conformance.suite.AlgorithmConformanceTests`. Generated tests inherit the suite, with a session-scoped
`algorithm_case` fixture and a `profile` fixture parametrized from repository registration. See the
[canonical acceptance inventory](tests.md#downstream-acceptance-suite) for each check and its purpose.
