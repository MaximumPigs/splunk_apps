---
hits: 1
seen: [2026-11-15]
area: git
level: lesson
---
**Symptom:** While building `splk loop`, commits reached `main` with no PR
(f2f4b32). VS Code's Git log showed `git push origin <branch>:main` at
2026-11-15 08:35:43 local (user setting `git.confirmSync` false).
**Cause:** The branch was made with `git checkout -b <branch> origin/main`, so
its upstream was `origin/main`. The editor's Sync action pushes a branch to
its upstream. A throwaway bare-repo repro showed plain
`git push -u origin <branch>` does not push to the tracked branch, so the
command the agent ran was not the culprit. The bash guard cannot see editor
actions: they are not tool calls.
**Fix:** `new_branch()` in `tools/splk/loop.py` uses
`checkout --no-track -B` then `branch --unset-upstream` (`-B` keeps an old
upstream). GitHub ruleset "Protect main" is now active: PR required, squash
only, CI required, no force push, no deletion (#21, #22).
**Catch earlier:** Create work branches with
`git checkout --no-track -b <branch> origin/main`, never tracking main. The
server-side ruleset is the only control that covers non-tool pushes. Promote
to `.claude/rules/` when seen again.
