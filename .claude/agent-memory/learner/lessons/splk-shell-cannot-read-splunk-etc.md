---
hits: 1
seen: [2026-11-14]
area: splk
level: lesson
---
**Symptom:** easyadmin 1.4.0, while checking whether a props copy reached
disk: the agent's shell could not read `C:\Program Files\Splunk\etc\apps\launcher\local`
("permission denied"), so a "file is missing" result from the shell meant
nothing.

**Cause:** on the owner's Windows machine Splunk's `etc/` belongs to the
service account; the agent's shell has no read access to some of it. A
failed read there is not evidence that a file is absent, in any app.

**Fix:** a temporary live probe calling the app's own conf-reading endpoint
(`/services/easyadmin/conf`, which reads files as splunkd's user) showed the
real disk state; the probe was deleted afterwards.

**Catch earlier:** never conclude from a shell read under
`$SPLUNK_HOME/etc`; read disk state through splunkd (an app endpoint or a
live test), and treat "permission denied" as "unknown".
