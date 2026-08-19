# Superseded PatchPackage v1 artifacts

Phase 3.3 bumped `PATCH_PACKAGE_SCHEMA_VERSION` to 2. v1 remains loadable
for audit; `act` rejects it as legacy/non-publishable.

| Artifact | Generator | Why it has no v2 replacement |
|---|---|---|
| `patch-6a0903434c41c909.json` | schema | Regenerating against current facts and the current site worktree is `NO_OP` — the 24-hour remedy window is already unpublished. The v1 package is the record of the change that landed. |
| `patch-da1e5e81bd692742.json` | sitemap | Replaced by `packages/patch-512fee715c69bf31.json` (v2). The v1 package cited the nominal `agent:sitemap-route-inventory` string; v2 cites `evidence/ev-route-inventory-8c0835d1b724.json`, a hash-bound route inventory. |
