# Research Vault — Obsidian is the IDE; the LLM is the programmer; the wiki is the codebase.

You (Claude) are the programmer. The human reads and steers in Obsidian; you write and refactor the wiki.
Human rarely edits wiki pages by hand. Human drops papers and asks questions. You compile knowledge.

## Analogy → concrete mapping

| Software                | Here                                                                 |
|-------------------------|----------------------------------------------------------------------|
| IDE                     | Obsidian: graph = call graph, backlinks = find-usages, Dataview = queries |
| Programmer              | Claude Code, using `/ingest`, `/query`, `/lint`                      |
| Codebase                | `wiki/` (sources, concepts, entities, syntheses)                     |
| Third-party dependency  | Papers: `<stem>/<stem>.pdf` + `<stem>.md` + `<stem>_artifacts/` (immutable) |
| Build / compile         | `/ingest` (paper → wiki pages)                                       |
| Linter / CI             | `tools/wiki.py lint` (exit 1 = build broken)                         |
| Entrypoint / README     | `wiki/index.md`                                                      |
| Commit history          | `wiki/log.md` (append-only) + git                                    |
| Style guide / types     | this file + `templates/`                                             |
| Tests                   | `/query` answers must cite wiki pages; ungrounded claims = bug       |

## Layout

```
papers.sh              docling pipeline: PDF in root -> <stem>/ folder (pdf, md, artifacts), git-committed
<stem>/                RAW paper. Never edit the .md/.pdf/artifacts. It is the "vendored dependency".
wiki/index.md          catalog of every wiki page, one line each. Update on every change.
wiki/log.md            append-only: `## [YYYY-MM-DD] ingest|query|lint | title` + pages touched
wiki/sources/<slug>.md one page per paper: summary, claims, method, results, limitations
wiki/concepts/<slug>.md ideas, methods, benchmarks, metrics (cross-paper)
wiki/entities/<slug>.md people, orgs, models, systems, datasets
wiki/syntheses/<slug>.md cross-paper comparisons, filed answers to good questions
templates/             page skeletons (copy, don't invent structure)
tools/wiki.py          `pending` and `lint`
.claude/commands/      /ingest /query /lint
```

## Pipeline

1. Human drops `foo.pdf` in vault root. `./papers.sh` (or `./papers.sh --watch`) runs docling →
   `foo/foo.pdf`, `foo/foo.md`, `foo/foo_artifacts/*.png`, then commits.
2. `/ingest` — you compile pending papers (`tools/wiki.py pending`).
3. `/lint` after ingest, and periodically.
4. `/query` for questions; file valuable answers back as `wiki/syntheses/`.

Docling lives in `.venv-docling/` (separate from `.venv/`, which serves the hydradna MCP server — do not mix).

## Coding standards for wiki pages

- **Links**: always vault-relative wikilinks without extension: `[[wiki/concepts/foo]]`, `[[foo/foo]]`.
  Never bare basenames (paper `foo/foo.md` and any page named `foo` would collide).
- **Slugs**: lowercase-kebab, meaningful. Rename opaque paper folders (e.g. `9ad8a465-…`) to a title slug
  with `git mv` BEFORE writing the source page, so the raw link is stable.
- **Frontmatter** required (lint enforces): source → `type, raw, created, tags`; others →
  `type, created, updated, sources, tags`. `type` ∈ source|concept|entity|synthesis. `sources` = list of `[[wiki/sources/x]]`.
- **Provenance**: every non-trivial claim carries a link back to its source page, and source pages cite
  section/figure/table of the raw paper (`[[foo/foo#3 Method]]`, artifact images via `![[foo/foo_artifacts/image_000003_….png]]`).
  Numbers copied from a paper must match it exactly. Unsure → say "unclear in source", never guess.
- **DRY**: before creating a concept/entity, search `wiki/` for it (and aliases). Update existing page instead of duplicating.
  Add `aliases:` in frontmatter for synonyms.
- **Contradictions**: don't silently overwrite. Add a `## Contradictions` section citing both sources.
- **No orphans**: every page needs ≥1 inbound link and an entry in `wiki/index.md`.
- **Write for reuse**: dense, factual, no filler. Prefer tables for comparisons.

## Workflows

### Ingest (compile)
1. `tools/wiki.py pending`. If PDFs sit in root unconverted, run `./papers.sh` first.
2. For each paper: read `<stem>/<stem>.md` fully (look at key figures in `_artifacts` if they matter).
3. Rename folder to slug if opaque. Create `wiki/sources/<slug>.md` from `templates/source.md`.
4. Create/update 5–15 concept & entity pages. Each update = add the new source to `sources`, bump `updated`, add the new info.
5. Update `wiki/index.md`; append to `wiki/log.md`.
6. `tools/wiki.py lint` must exit 0. Fix, then commit: `git add -A && git commit -m "ingest: <slug>"`.

### Query (run)
Read `wiki/index.md` first, then relevant pages, drill to raw paper only when the wiki lacks detail.
Answer with citations to wiki pages. If the answer is reusable, file it under `wiki/syntheses/` and log it.

### Lint (CI)
Run `tools/wiki.py lint`; fix errors. Then judgment checks: stale claims superseded by newer papers,
concepts mentioned in 3+ pages without their own page, missing cross-links, contradictions unflagged.
Log the run.

## Guardrails

- Raw paper folders are read-only, except the rename-to-slug step at first ingest.
- Don't touch `.obsidian/` plugin data or `.venv*/`. The `karpathywiki` plugin's auto-ingest is OFF on purpose
  (a small local model produced junk in a sibling vault) — Claude is the ingest engine.
- `.mcp.json` / `.claude/settings.json` hydradna hooks are unrelated infra; leave them.
- Commit after each ingest, small and atomic. Never rewrite `wiki/log.md` history.
