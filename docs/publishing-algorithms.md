# Publishing an implemented algorithm

Newly generated repositories include package metadata, a distribution check, a manual publishing
workflow, and their own `RELEASING.md`. Copier asks for `package_name`, `repository_url`, and
`license_expression`; the latter two may remain blank during implementation, but must be completed
before publishing. Licensing remains the algorithm author's choice.

The guide below is rendered directly from the generated guide with example names, so these instructions
are maintained in one place. For an existing generated repository, use `copier update` and review its
changes, especially existing metadata and CI customizations. The current published generator 0.4.0a2
predates this support; use the template revision containing this change until the next generator release.

<!-- algorithm-release-guide -->
