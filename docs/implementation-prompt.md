# Copyable algorithm-implementation prompt

Use the [interactive prompt builder](https://meds-algorithm.readthedocs.io/en/latest/prompt-builder/)
or fill in the fields below. The agent inspects sources and selects profiles before generating a new
local or GitHub repository. The builder runs locally in your browser; it does not launch an agent.
The provided `real_data` test remains the MIMIC-IV demo smoke test, independent of supplied evaluation tasks.

The prompt adapts [Ponytail's implementation principles](https://github.com/DietrichGebert/ponytail/blob/main/skills/ponytail/SKILL.md)
to scientific algorithm development. It works with Claude and other coding agents without installing a plugin.

```text
Implement a MEDS algorithm from the following inputs.

Paper(s), supplementary material and versions:
<PAPER_REFERENCES_OR_NOT_SUPPLIED>

Code/repository source(s), revisions, configurations and checkpoints:
<CODE_REFERENCES_OR_NOT_SUPPLIED>

Destination (a NEW local repository or a NEW GitHub repository, including visibility):
<NEW_REPOSITORY_DESTINATION>

Local working directory for the new repository:
<NEW_LOCAL_REPOSITORY_PATH>

Profile selection (automatic, or an explicit list of one or more profiles):
<PROFILE_SELECTION>

Dataset context (name, revision and MEDS path, if available):
<DATASET_CONTEXT_OR_NOT_SUPPLIED>

Already prepared evaluation tasks (labels location, task-config location, bundle revision and
optional task subset; or explicitly not supplied):
<PREPARED_TASK_BUNDLE_OR_NOT_SUPPLIED>

Work scope (implementation/local tests, also MEDS-DEV integration, or preparation for full evaluation):
<WORK_SCOPE>

Scientific ambiguity mode (confirmation required by default; exploratory only if explicitly enabled):
<SCIENTIFIC_AMBIGUITY_MODE>

Additional implementation constraints:
<ADDITIONAL_CONSTRAINTS_OR_NONE>

Inspect the supplied sources before generating the repository. If both paper and code are provided,
compare them, record discrepancies and identify which behavior is implemented; do not silently assume
one always overrides the other. If only a paper is provided, distinguish source-backed choices from
necessary assumptions. If only code is provided, inspect its revision, configuration and checkpoint
requirements; do not claim fidelity to an unavailable paper.

Resolve scientific ambiguities before implementing the affected behavior. Check the paper, supplements,
official code and available configurations first; record sources and material conflicts. Ask whether two
reasonable interpretations could produce materially different algorithms or change what evaluation measures.
A missing learning rate or batch size can usually use a plausible, configurable default with its rationale
recorded, unless that choice is central to the scientific claim. Missing feature construction, temporal
aggregation, architecture components or training objectives are material ambiguities, not routine defaults.

In confirmation-required mode (also the default if no mode is supplied), pause dependent implementation
and request confirmation for a material unresolved ambiguity. Explain what is missing, the evidence
consulted, plausible interpretations and their consequences; recommend an option when justified. Continue
independent work while waiting. An earlier explicit decision covering the same choice is sufficient unless
new evidence or a scope change invalidates it; silence is not confirmation.

Only when exploratory mode is explicitly enabled may you implement provisional interpretations of material
algorithm-design ambiguities without first obtaining a decision. Record each as provisional before using
it, expose the choice in configuration where appropriate, and label affected code, tests and results as an
exploratory adaptation. Require review of these decisions before claiming faithful reproduction. Do not
present an assumption as source-backed behavior or silently substitute a familiar method for a missing one.

In BOTH modes, ambiguities about leakage, permitted label access, cohort/target definitions or evaluation
validity remain blocking for dependent work until explicitly resolved. Exploratory mode does not authorize
changing supplied tasks, weakening acceptance tests, accessing data or running demo/full-data/cluster jobs
without the existing approvals. Record the mode, routine defaults, unresolved questions, provisional choices
and explicit decisions in IMPLEMENTATION_REPORT.md under "Scientific assumptions and decisions"; update the
existing report rather than creating another specification file.

RAW-DATA ACCESS GUARD (all profiles, modes and stages): Do not directly open, read, sample,
preview, print, grep, query, dump, export or otherwise inspect real patient-level records, raw MEDS
event files or underlying clinical tables through the agent session, shell commands, notebooks or
ad hoc scripts. A supplied data path, credentials, exploratory mode or implementation request is
NOT authorization to inspect raw data. Use synthetic fixtures for implementation and local tests;
source code, documentation, schemas and non-sensitive metadata may be inspected. Only after explicit
human approval for a specific demo or full-data gate may the approved, auditable algorithm pipeline
process real MEDS inputs programmatically for that run. Approval to execute the pipeline does not
authorize the agent to browse records or expose raw rows in output, logs, reports, chat or commits.
If direct record inspection seems necessary for debugging, stop and request separate, narrowly scoped
human approval before doing so. Keep evaluation outcomes out of scoring and use the core key-only
index reader for prediction keys when the relevant data access is authorized.

For automatic profile selection, choose one or more profiles supported by documented source behavior:
supervised, finetune, probe, zero_shot_direct, zero_shot_materialized or predict_only. Record evidence for
each choice and proceed when the evidence is clear. Do not add speculative capabilities merely because
a profile exists. For an explicit list, implement that scope; report material incompatibilities before
implementing unsupported behavior, and do not silently replace or expand it. Shared methods may be
implemented once through multiple profile inheritance when their semantics match, or through separate
classes with shared components. Each selected profile gets its own MEDS-DEV YAML and acceptance tests.

Generate the new repository with the MEDS algorithm template at
https://github.com/McDermottHealthAI/MEDS_algorithm_template using a reviewed immutable revision, and
record it in .copier-answers.yml. Pass the selected profiles explicitly; do not accidentally accept the
single-profile default. Never overwrite an existing local directory or GitHub repository. For a local
destination, initialize Git without creating a remote. For a GitHub destination, create the specified
repository with the specified visibility and connect the local checkout; report missing access without
changing the destination or visibility. Respect any more specific workspace repository-routing rules.

Supplied evaluation tasks are already prepared: use their labels and task configs as fixed inputs.
Verify their dataset/revision, task identities, splits, prediction times and consistency before use.
An optional task subset selects only tasks already present in that bundle. Do not generate new tasks,
extract new labels, relabel examples or silently modify the task definitions. Use supplied indices or
read only the supplied prediction keys through the core index reader; evaluation outcomes must never
enter scoring. Zero-shot profiles additionally require executable task criteria and matching predicates.
If the bundle is not supplied, continue implementation and synthetic tests; report evaluation as
pending. An incomplete bundle blocks only the dependent evaluation, not unrelated implementation.

Read AGENTS.md, SPEC.md, README.md, and docs/IMPLEMENTATION_GUIDE.md in the generated repository
completely before writing code. Inspect the paper, supplementary material, source repository,
configuration files, checkpoints, preprocessing code, and evaluation code available from the supplied
source.

Apply the Ponytail principle of the smallest complete change: implement the complete source-defined
algorithm with the least additional infrastructure. Check meds-algorithm, existing algorithm-family code,
standard libraries and installed dependencies before creating helpers. If the source ships an installable
package or executable, depend on it pinned to the exact reviewed revision and call it; write only contract
glue (label-free preprocessing, cohort/key adaptation, explicit key association, coverage). Install it in the
algorithm environment; if it breaks meds-algorithm within core's declared dependency ranges, fix core. For a
genuine conflict with core, run the source as an external executable from a separate environment that the
algorithm package creates and manages (committed lockfile, built at install or first use, digest recorded in
manifests; MEDS-DEV installs only requirements.txt). Reimplement only when the source cannot run even in
isolation or its code cannot meet the contract even with glue, and record why in IMPLEMENTATION_REPORT.md;
local hardware alone is not a reason, since CPU or other hardware is acceptable.
Choose an algorithm_slug that does not shadow the source's distribution or import name (for example
genhpf_meds, not genhpf), so both can be installed together. Keep shared fixes in their
owning package; do not copy core utilities into the algorithm repository. Avoid speculative wrappers,
configuration options and compatibility layers. Trace affected commands, callers, fixtures and
documentation, and finish all required changes. Simplicity must preserve scientific fidelity, temporal
and label isolation, artifact validation, reproducibility, required evaluation evidence and human
review gates. Write focused tests for new behavior and failure cases. Report deviations and checks
that were not run.

Write minimalist, auditable, object-oriented algorithm code. Put source-defined hyperparameters and defaults
in the algorithm-owned frozen <AlgorithmClass>Config class in config.py; validate values and prove
serialization round trips. Keep the implementation in <algorithm_slug>.py and expose the named algorithm
and configuration classes from the package, so callers can import them meaningfully.
Keep the public API intentional and small. Classes, functions and modules used only inside the implementation
should use a single leading underscore (for example _FeatureEncoder or _features.py) and should not be
re-exported from the package __init__.py. List only intended public exports in __all__. Keep contract-required
methods and integration hooks publicly named where required. A leading underscore signals an internal,
unstable interface in Python; it does not enforce access control. Prefer it over double-underscore name
mangling unless avoiding a specific inheritance collision. Do not create extra classes just to organize
private helpers, and do not hide the algorithm/configuration classes callers are expected to import.
For neural algorithms with matching semantics, extend core NNConfig rather than
duplicating shared capacity, learning_rate, batch_size, weight_decay and dropout settings. Define
source-backed defaults and the capacity-multiplier mapping (reference architecture, dimensions, rounding
and minimums); call super().validate() for inherited
constraints. Test that the settings actually control construction/training. See the installed architecture
guide for units, extension examples and scaling ownership. Keep cohort selection upstream; record actual
parameter counts and consumed data separately rather than inferring them from capacity or a data fraction.
Use inherited additional_predicates_file for dataset-specific feature additions when needed. Read the
runner-resolved request.predicates_file in preprocessing; do not override base definitions, merge again,
or change task predicates. Preserve temporal isolation and use the same configuration across steps.
Implement the selected Algorithm profile methods with their typed request classes. Prefer small cohesive
components and explicit constructor dependencies; use inheritance for the profile contract and composition
for algorithm internals. Do not add unnecessary classes, wrappers, mutable module-level runtime state, hidden
singletons, import-time work, broad exception swallowing, or duplicated contract tables. Declarative
constants and the profile-to-implementation association are appropriate; fitted state belongs in artifacts.
Use core's runner for both CLI execution and tests. Algorithm methods write only to its staging destination
and return PayloadMetadata; do not reimplement publication, measurements or manifest/config/request writing.
Implement explicit payload compatibility checks. Prediction outputs contain keys and probabilities;
only the runner attaches evaluation truth after scoring. Demonstrate that saved configuration and requests
can be reloaded in a fresh process and executed without an earlier call on the same algorithm instance.

Preserve all selected algorithm profiles and standardized command arguments, MEDS input boundary, artifact
manifest envelopes, MEDS-DEV model.yaml interface, and final MEDS prediction output. Intermediate payload
formats and execution mechanisms are algorithm-owned: choose whatever preprocessing, featurization, framework,
batching or non-batching strategy, external executable, storage format, and algorithm architecture most
faithfully reproduce the source.

When predicates are needed, reuse MEDS-DEV predicates for the selected dataset if available; otherwise,
use reviewed external predicates for that dataset and record their provenance. Decide within the algorithm
how those predicates become inputs. Validate dataset-specific codes, units, task definitions, and label mappings;
do not assume MIMIC mappings apply to another dataset. Keep such mappings in dataset-specific
configuration or algorithm-owned code. Do not introduce a generic predicate-derived feature representation
into the contract package. Keep the provided MIMIC-IV demo code, task, and MEDS-DEV predicates as the
canonical smoke test, regardless of the full-data target.

For a zero_shot_direct algorithm (answers queries directly, e.g. MOTOR, EveryQuery) or a zero_shot_materialized
algorithm (generates futures and evaluates the task on them; infer is task-independent and only predict
receives the task): the algorithm receives the original ACES task through
external_task_criteria_file (with the dataset predicates) and the upstream-built index through
external_index_dir. Never build, filter, or extend the cohort, and read the index only through
meds_algorithm.read_index. Reuse an existing aces-to-<algorithm> adapter for this algorithm if one exists;
otherwise write one on aces-relaxations, pinned to an exact version: reject tasks that are not future-only
or are degenerate, normalize, then apply only the approximations and assumptions the algorithm's query
language forces. Publish relaxations.yaml with each zero-shot prediction artifact, and report per task whether
the answer is exact.
A materialized algorithm evaluates the task on generated futures instead and needs no relaxation beyond
sampling. Follow the shape for the selected profile in docs/IMPLEMENTATION_GUIDE.md.
Do not omit source behavior because it is inconvenient for a fixture; adapt the implementation or fixture
instead.

Record every material source element as ported, adapted, or omitted, with evidence and justification, in
IMPLEMENTATION_REPORT.md. Implement every selected typed algorithm method, finalize the implementation-specific
command strings in model.yaml, and implement tests/e2e.py. Configure representative config instances
in tests/conftest.py. Keep TestConformance inheriting the shared meds-algorithm acceptance suite;
do not copy its test bodies or override its checks to suppress failures. Remove each profile from STUB_PROFILES only
after that profile completes and produces standards-conformant predictions; complete every selected profile.

Always run:

    uv run pytest -rs

Also run `bash scripts/check_distribution.sh` to verify installed imports, CLI commands and bundled
defaults outside the checkout. Extend `tests/wheel_smoke.py` for required algorithm configuration or
resources. Follow RELEASING.md for publication readiness; package publication itself requires an explicit
user request. Do not choose a license on the user's behalf or bundle datasets, credentials or fitted weights.

If the selected scope includes MEDS-DEV integration or full-evaluation preparation, also run:

    uv run pytest -m meds_dev -rs

For implementation/local-tests scope, finish with implementation and local validation evidence. For
MEDS-DEV integration scope, finish after its integration evidence. Report unavailable dependencies or
adapters explicitly; do not weaken tests. The following demo and full-data stages apply only when the
selected scope is preparation for full evaluation; selecting that scope is not execution approval.

Complete the pre-demo sections of IMPLEMENTATION_REPORT.md and ask for human review of source fidelity,
predicate interpretation, and the proposed MIMIC-IV demo execution. Only after approval, run:

    uv run pytest -m real_data -rs

There must be zero algorithm_stub skips. Report exact pass/skip counts and account for every remaining skip.
Update IMPLEMENTATION_REPORT.md with the demo cohort, final-output coverage, predicate provenance,
environment, wall time, peak process-tree PSS/RSS, GPU measurements when available, failures, and fixes.
Ask for a second human review before launching the selected full dataset through the repository's SLURM
interface. Review target-dataset compatibility, access, and resources separately from the MIMIC-IV demo.
Use the supplied, already prepared task bundle for the selected dataset. It must contain task configs,
per-task labels/keys and split assignments; zero-shot runs additionally require the original ACES criteria
and matching predicates. Do not generate or extract replacement evaluation tasks. Canonical synthetic
fixtures and the built-in MIMIC-IV demo smoke task remain separate from this supplied evaluation bundle. If the bundle is absent
or inconsistent, report the evaluation blocker and the exact missing inputs.
Record the dataset name/revision, predicate provenance, bundle location, supplied bundle revision and
available upstream build provenance, and a digest of its task definitions. Keep the bundle external to Git.
Commit the implementation, configuration and report-so-far; push when a remote is configured. Run the
cluster job from that exact clean commit. After the authorized run, complete the report with full-data evidence, scientific deviations, and known limitations, then
synchronize structured results through the GitHub workflow when the destination has a GitHub remote.
For a local-only repository, retain the committed report and run evidence locally. Treat
docs/IMPLEMENTATION_GUIDE.md as the authority for the ordered gates and their evidence.
```
