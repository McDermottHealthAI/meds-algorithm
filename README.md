# meds-model-core

Shared contracts and reusable infrastructure for MEDS model repositories. This is an alpha: the contract and initial extractions are implemented; the remaining module boundaries are planned.

Implemented now: shared profile/command definitions, strict split selection, key-only index reading,
and the single versioned contract document. Other module directories mark planned extraction ownership;
they do not claim implementations that have not yet been migrated and tested.

```text
meds-model-core/
├── pyproject.toml
├── README.md                    # package layout, development and extraction status
├── src/meds_model_core/
│   ├── CONTRACT.md              # the only normative contract, included in the wheel
│   ├── spec.py                  # meds-model-core-spec: read the installed version's contract
│   ├── contracts/commands.py    # Command, StepSpec, ArtifactInput, profiles, dispatch
│   ├── data/index.py            # strict split selection and key-only projection
│   ├── artifacts/              # next: manifest, publication, compatibility, digests
│   ├── runtime/                # next: process resources and subprocess utilities
│   ├── tasks/                  # next: TaskSpec and relaxation ledger
│   ├── evaluation/             # next: prediction validation and post-score truth join
│   ├── integrations/           # next: MEDS-DEV registration and argument adaptation
│   └── conformance/            # next: reusable assertions/fixtures, optional test dependencies
└── tests/                      # package behavior and packaging-resource checks
```

The [template](https://github.com/florian6973/MEDS_model_template) re-exports extracted APIs
and pins an exact commit of this repository. This alpha is installable from Git; no PyPI release is
required. Upgrade the dependency pin through a reviewed change in each consumer.

```bash
uv sync --extra test --group dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
uv run meds-model-core-spec
```

To install without a checkout, use `pip install 'meds-model-core[data] @
git+https://github.com/florian6973/meds-model-core.git@<full-commit-sha>'` (on one line).
Generated repositories record the actual immutable SHA in their dependency declaration.

The root `README` explains use; `CONTRACT.md` defines normative behavior. Generated `SPEC.md` files are
short pointers to the installed core version, not copies. The documentation site includes that same
source file. API reference pages link to it instead of maintaining another argument table. Model
repositories keep only their own implementation decisions, supported profiles and evidence.

Family sharing belongs in **one repository per model family with multiple profiles** where appropriate:
for example one MOTOR implementation with fine-tuning/probing/direct-query adapters. Family-specific
tokenizers, objectives, pooling and task translators stay there, outside the generic core. The 15 existing
repositories are not merged or changed by this scaffold.

## Extraction sequence

1. Contracts, index projection and canonical documentation: implemented in this package.
2. Artifacts/provenance/runtime: reconcile the four existing manifest variants; fix publication rollback
   and process-tree sampling defects before extracting. Test failure paths and compatibility decisions.
3. Task/evaluation helpers: separate label reads from index reads and evaluation-only truth attachment;
   test absent/conflicting splits, duplicated keys and forbidden-label access.
4. MEDS-DEV/conformance: migrate registration and reusable assertions; retain model-owned execution hooks,
   CLI stubs, profile YAML, CI and editable cluster policy in the template/model repository.
5. Build/publish the alpha, pilot a tabular model and a multi-profile neural family, then open tested
   dependency-update PRs. Remove local compatibility implementations as each shared module becomes canonical.

The core stays independent of Torch, JAX, Lightning, FEMR, XGBoost and ACES model adapters. Data/test
dependencies are extras. Future runtime GPU integrations must be optional. Package upgrades and
scientific model revisions remain separately reviewable changes.
