---
description: Log the latest applied changes to docs/journal.md via the journal-logger subagent
---

Delegate to the `journal-logger` subagent to record the changes applied so
far in this session (or the current working-tree diff, if invoked outside
an active work session) as a new dated entry in `docs/journal.md`.
