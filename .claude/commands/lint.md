---
description: Run wiki linter + semantic health checks, fix problems, log the run
---
Follow **Workflows → Lint** in CLAUDE.md. Run `tools/wiki.py lint`, fix every ERROR, resolve WARNs
(orphans, pending), then do the judgment checks. Append a `lint` entry to `wiki/log.md`. Commit.
