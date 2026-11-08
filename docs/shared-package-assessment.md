# Template and shared package

The template should generate repository structure, algorithm command stubs, profile descriptors, test
adapters, CI and cluster configuration. Executable infrastructure that needs coordinated bug fixes
belongs in the versioned `meds-algorithm` dependency. The [shared core package](core-package.md) now
contains the reusable template infrastructure and conformance helpers, and owns the canonical
specification. It is available from its public Git repository; downstream migrations remain separate.

An inspection of 12 local algorithm-repository snapshots found 5,087 lines across their copied contract
modules. Four modules are byte-identical in all 12: `contract.py` (86 lines), `results.py` (76),
`meds_dev.py` (31), and `__init__.py` (16). `manifest.py` has four variants across groups of 5, 3, 2 and 2
repositories. These are physical source-line counts, not a claim that every line is safely extractable.
The private remotes could not be refreshed during this assessment; conclusions concern the inspected
local `origin/main` snapshots, not verified current remote heads.

| Destination | Candidates | Qualification |
|---|---|---|
| Core runtime | Profile ABCs, typed requests/configuration, shared runner, manifest schema and compatibility checks, provenance, artifact publication, wall-time and process-tree measurements, structured results, MEDS-DEV registration | Core owns these implementations, including replacement rollback and worker-thread child discovery; downstream algorithms still need migration. Keep GPU/framework integrations optional. |
| Optional conformance package | Prediction schema/key checks, integration provisioning, train-only canaries, generic synthetic signal fixture | `meds_algorithm.conformance.meds_dev` and `meds_algorithm.conformance.signal` are identical in 11 repositories. Keep algorithm execution and feature inspection as adapters. |
| Shared data-boundary helpers | Explicit split selection, label-blind index reading, uniqueness/conflict validation, keyed prediction writing | Existing helpers disagree on duplicate and split behavior. Specify one fail-closed policy before extraction. |
| Family repositories | MOTOR FT/LP backend/provenance utilities; MEDS-Tab large/LR tabularization and runtime; MEDS-EIC-AR and supervised variant tokenization/I/O/runtime | Prefer one repository per family with multiple profiles and shared internal modules; keep algorithms outside the generic core. |
| Template/algorithm repository | Algorithm architectures, objectives, feature semantics, task translators, pooling, trajectory generation, tuned defaults, concrete integration adapters | Their apparent similarity does not make them backend-neutral. |

Examples of exact family-level copies include MEDS-Tab runtime (159 lines), MOTOR FT/LP provenance
(86 lines), and MEDS-EIC-AR I/O (224 lines). Additional identical functions occur across algorithm families,
including dataset identity and artifact checks. Some dataset-identity helpers hash only paths and file
sizes, which is insufficient to prove content equality. A common implementation must first resolve
that semantic problem rather than preserve it more widely.

## Update algorithm

1. Publish the audited runtime with a documented supported contract version and optional test extras.
2. Pilot two structurally different algorithms and test a multi-profile family repository before migrating all.
3. Replace copied contract/runtime modules with pinned package dependencies. Keep the import
   namespace stable where possible, and verify installed package discovery cannot select a stale local copy.
4. Use dependency-update PRs in every private algorithm repository to move runtime versions and rerun its
   conformance adapters. Use Copier updates for changes to scaffolding and workflow files.
5. Treat contract-major upgrades as explicit migrations, not automatic cross-repository rewrites.

This avoids maintaining an updater that copies Python implementation files into every algorithm. One
shared-package release makes a fix available everywhere; each repository adopts it through a visible,
tested dependency change. Algorithm implementations retain their own release and scientific-validation gates.
