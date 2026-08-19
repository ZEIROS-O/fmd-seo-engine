# Scheduler activation — prepared, not enabled

Recorded 2026-08-19. `\FMD-SEO-Daily` is still **Disabled**. Nothing was
published, pushed, or run on a schedule.

## What exists now

- Worktree: `.worktrees/fmd-seo-scheduler-state` on branch
  `automation/fmd-seo-state` at `761e1a5` (the Phase 1–3 remediation HEAD).
  Branched from the remediations, not `origin/main`, so an accidental enable
  would run the guarded `bin/fmd-seo-cron`, not the pre-Phase-1 wrapper.
- Primary checkout SHA was `258f9ef` before the worktree add and
  `258f9ef` after. Unchanged.
- Repo `bin/run-fmd-seo-cron-hidden.vbs` already points at this worktree.
  The copy at `C:\Users\lucas\Scripts\` was **not** overwritten.

## What Lou still has to do

1. Review this branch. Do not enable until he is willing to run the
   remediations, not `origin/main`.
2. Deploy the repo `.vbs` to `C:\Users\lucas\Scripts\`
   (`bin/register-fmd-seo-task.ps1` does that and registers the task).
3. Canary: one manual `bin/fmd-seo-cron` from the scheduler worktree.
   Prove the primary checkout SHA and status are unchanged, only
   allowlisted paths were staged, no push.
4. A second consecutive substantive scheduled run.
5. Only then set `\FMD-SEO-Daily` to Ready.

Two consecutive substantive scheduled runs have **not** happened. Activation
is not stable.
