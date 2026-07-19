# Release manifest

Immutable RC manifest produced by `tools/release-gate/generate_release_manifest.py`.

Freeze rules after RC tag:

- No feature, prompt, model profile, semantic metric, policy, connector, dependency, or test dataset changes
- Fixes require new `rc.N+1`; prior RC evidence does not auto-carry

Promotion compares: image digest, prompt hash, model hash, policy version, semantic version, migration version, feature flags, IaC module version.
