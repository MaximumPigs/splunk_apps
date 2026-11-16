---
hits: 1
seen: [2026-11-17]
area: splk
level: lesson
---
**Symptom:** working the Tooling roadmap items from a git worktree, `splk` live
and UX runs could not reach the target: copying the env file into the worktree
was denied, and a wrapper pointing the worktree's `splk` at the main checkout's
env file was denied as a workaround.
**Cause:** the secrets file lives only in the main checkout and the guards
refuse copying or redirecting it, so anything needing the token (live, UI, UX,
deploy) cannot run from a worktree. Unit tests need no secrets and do run.
**Fix:** check the branch out in the main checkout for live/UX runs; use
worktrees for unit-test-only work.
**Catch earlier:** decide before starting: if the item needs `splk dev`, work in
the main checkout. Do not try to route around the denial.
