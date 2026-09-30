---
description: Compile pending paper(s) into the wiki (source page + concepts + entities + index + log)
argument-hint: "[paper-folder-stem ...]  (default: all pending)"
---
Follow **Workflows → Ingest** in CLAUDE.md exactly.
Target: $ARGUMENTS (if empty, run `tools/wiki.py pending` and ingest all).
Run `./papers.sh` first if unconverted PDFs sit in the vault root.
Finish with `tools/wiki.py lint` (must exit 0), then commit. Report: pages created, pages updated, contradictions found.
