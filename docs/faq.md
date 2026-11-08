# FAQ

## Why can't my algorithm build or filter its own cohort?

Because then two algorithms could be evaluated on different patients and nobody would notice. The index and
its labels come from one extraction run upstream (MEDS-DEV's `meds-dev-task` for the demo, a shared,
reviewed task bundle for full data). An algorithm predicts every requested row; rows can be left out
only under a declared exclusion policy that lists them.

## My algorithm needs a statistic over the whole dataset. Can I compute it on all splits?

No. Fit vocabularies, frequencies, bins and normalizers on `train` only. Computing them over all splits is
transductive leakage: it uses held-out patients' data even though it never touches a label.

## Why do some algorithms run in two Python environments?

Because their dependencies cannot coexist. An algorithm's training stack may pin an older `meds` (for example
femr 0.2.4 requires `meds==0.3.3`), while the ACES tooling a zero-shot adapter uses for task translation
(aces-relaxations, es-aces ≥ 0.7.3) requires `meds ≥ 0.4`. The two sides can run in separate environments
and exchange only files. The contract does not care how a command
is executed, so this is allowed; document it in the repository.

## What does it mean that a task is "refused"?

A zero-shot algorithm must raise rather than answer a task it cannot pose; the command fails and writes no
predictions. The common case is a direct algorithm given a task whose label is not *future-only* in
aces-relaxations' structural sense — for example MEDS-DEV's `mortality/in_icu/first_24h`, whose `gap`
window is anchored at the trigger and straddles the prediction time. A re-anchoring step makes it
posable; see [Zero-shot in practice](zero-shot.md#windows-that-straddle-the-prediction-time).
Materialized algorithms are not affected.

## Why is the AUROC on the MIMIC-IV demo undefined (or meaningless)?

The demo has 100 patients. For `mortality/in_icu/first_24h` the held-out split has a handful of rows and
may have no positive label at all, in which case AUROC is undefined. Training rows cannot stand in for a
pretrained algorithm: pretraining saw those patients' futures. The demo gate validates that the pipeline runs
on real data — formats, scale transitions, coverage, resources — not how good the algorithm is. Performance
comes from the full-data run.

## My algorithm writes several files next to `predictions.parquet`. Is that allowed?

Yes, with one rule: every parquet file in the predictions artifact must be a predictions file. MEDS-DEV
evaluates every `**/*.parquet` under the predictions directory, and the key check does the same. Store
supporting tables — a zero-shot query bundle, a coverage table — in another format such as Arrow IPC;
`relaxations.yaml` and JSON files are fine.

## How do the tests catch label leakage and transductive fitting?

The end-to-end check validates the original run and a fresh full-lifecycle rerun:

- **Label leakage:** every stage runs again with evaluated outcome columns removed (all outcomes for
  zero-shot). Separate input roots remain separate; permitted training/context labels are retained.
  Both runs use the recorded fixture seed and deterministic settings. They must produce the same keyed
  scores within the contract's tolerance. Original and rerun probabilities are checked across every shard.
- **Transductive fitting:** `meds_algorithm.conformance.signal.add_split_canaries` gives every tuning and held-out subject a
  canary code that no training subject has. Your `fitted_codes(artifacts)` hook reports every code the
  algorithm fitted a statistic for (vocabulary, frequencies, bins); no canary may appear in it.

## Can a non-zero-shot algorithm use the ACES task?

Only `predict_only` may accept optional `external_task_criteria_file` as provenance, with
`semantics_digest: null`. Other non-zero-shot commands reject it. Supervised, finetune and probe algorithms
learn the task from its labels.

## What does `scripts/github-sync.sh` push?

Only `runs/<run-id>/spec.yaml` (dataset name and counts, task, predicates digest), `runs/<run-id>/result.yaml`
(status, git commit and dirty state, environment, SLURM job id, per-command resource summary) and
`runs/<run-id>/manifests/*.yaml`, on a `runs/<algorithm>/<run-id>` branch with a draft PR. It never pushes
predictions, labels, data, checkpoints, raw logs or metrics. The template computes no metrics at all:
MEDS-DEV's evaluation step (meds-evaluation) does.

## How do I bring template changes into an existing repository?

Review your working tree, then run in the generated repository:

```bash
copier update --trust
```

The repository's `.copier-answers.yml` records the template source, revision and answers, so Copier can
apply the template's changes as a three-way merge. Render from the Git URL rather than a local checkout so
updates work on every machine.

## Where is the authoritative rule for X?

In the [specification](reference/spec.md), which this site renders from core's `src/meds_algorithm/CONTRACT.md`.
Generated repositories' `SPEC.md` points to the contract in their installed core version.
