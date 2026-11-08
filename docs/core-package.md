# Shared core package

The core lives in its own [repository](https://github.com/McDermottHealthAI/meds-algorithm), pinned by the template to PyPI version `0.4.0a5`.
See its [layout and usage](https://github.com/McDermottHealthAI/meds-algorithm/blob/v0.4.0a5/README.md) for its artifact, runtime, task, evaluation, integration and conformance APIs.
The [specification](reference/spec.md) and [architecture and UML](reference/architecture.md) are
rendered directly from this core checkout, the same sources included in its distributions.
The `latest` documentation follows core `main`; generated algorithms use their pinned installed release.

`AlgorithmConfig` is the shared configuration parent. Neural implementations can extend `NNConfig`;
the [neural configuration and scaling guide](reference/architecture.md#neural-network-configuration-and-scaling-experiments)
shows a concrete subclass, YAML settings and a capacity sweep. It also explains why data-subset selection
belongs upstream and which measurements an algorithm must report for a later scaling-law analysis.
The template keeps this example in the core guide rather than maintaining a second specification.

Family-specific sharing belongs in one algorithm-family repository with multiple profiles and shared internal
modules. Tokenizers, neural architectures, objectives and algorithm-specific task translators stay there.

Generated repositories import `meds_algorithm` directly. Their package contains a typed algorithm
implementation and an algorithm-owned immutable configuration. `tests/e2e.py` invokes the same shared runner
as the CLI and supplies fitted-feature inspection hooks.
Reusable assertions, fixtures and MEDS-DEV provisioning live in core. No compatibility package is copied.

Publication uses exclusive writers and overwrite rollback. Algorithm provenance must be supplied explicitly;
the installed package cannot infer an algorithm checkout. See the core README for crash recovery, reader
visibility during overwrite, optional dependencies, and measurement limits.
