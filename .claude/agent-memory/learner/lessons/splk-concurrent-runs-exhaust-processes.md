---
hits: 1
seen: [2026-11-15]
area: splk
level: lesson
---
**Symptom:** easyadmin `splk dev` unit stage went red (5 failed, 834 passed, in 13s instead of the usual 33s): `git init` exited 3221225794 (0xC0000142, process failed to initialise) and four `test_splk_ux` tests died with "Connection closed while reading from the driver" (Playwright). The same tree, unchanged, passed 843/843 on the next run. Two `build` rows 4 seconds apart show overlapping `splk` invocations.
**Cause:** overlapping `splk` runs (or leftover browser/driver processes) exhausting Windows process resources; subprocess-spawning tests fail with startup errors that say nothing about the code.
**Fix:** none in code; re-run once with nothing else running. A failure that is a process-start code (0xC0000142) or a Playwright driver disconnect, with no assertion text, is environmental.
**Catch earlier:** run one `splk` command at a time. Do not "fix" the tests for these errors; only investigate if the re-run fails the same way.
