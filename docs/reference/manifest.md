# Reading artifact manifests

The [normative manifest schema](spec.md#4-intermediate-artifacts) and
[measurement schema](spec.md#6-measurements) live in the core contract. This page does not duplicate
their field tables.

When comparing runs, check the producer and payload format, configuration digest, source revision,
input content identities, and task semantics before comparing measurements. A configuration hash alone
does not identify the dataset or weights. A copied path is provenance, not proof of compatibility.

`null` means not measured or not applicable; zero is an observed value. Sampled live process-tree
memory and scheduler peak memory measure different things. Coverage counts are diagnostics; compare
actual prediction keys with the requested index.

Core's runner uses `measured_artifact` for publication and measurements. Pass `repo=algorithm_root` explicitly
to identify the algorithm checkout. Overwrite preserves a backup until publication succeeds; a failed
replacement restores it, or reports its recovery path if restoration also fails. New outputs use one
rename; overwrite uses two and can briefly hide the destination. Prefer immutable artifact paths for
concurrent readers. See the [core package](../core-package.md) for implementation ownership and limits.
