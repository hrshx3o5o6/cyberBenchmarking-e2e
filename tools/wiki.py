#!/usr/bin/env python3
"""Wiki 'compiler': deterministic checks so the LLM-programmer gets fast feedback.
  tools/wiki.py pending   papers converted by docling but not yet ingested
  tools/wiki.py lint      broken links, orphans, bad frontmatter, index gaps
Exit code 1 if lint finds errors (like a failing build)."""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
FM = re.compile(r"\A---\n(.*?)\n---\n", re.S)
KINDS = {"sources": "source", "concepts": "concept", "entities": "entity", "syntheses": "synthesis"}
REQ = {
    "source": ["type", "raw", "created", "tags"],
    "concept": ["type", "created", "updated", "sources"],
    "entity": ["type", "created", "updated", "sources"],
    "synthesis": ["type", "created", "updated", "sources"],
}
NON_PAPER_DIRS = {"wiki", "tools", "templates"}


def skip(p: Path) -> bool:
    return any(part.startswith(".") for part in p.relative_to(ROOT).parts)


def all_md():
    return [p for p in ROOT.rglob("*.md") if not skip(p)]


def frontmatter(p: Path) -> dict:
    m = FM.match(p.read_text(errors="ignore"))
    d = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.startswith((" ", "-")):
                k, v = line.split(":", 1)
                d[k.strip()] = v.strip()
    return d


def resolve(target: str, known: dict, bases: dict):
    t = target.strip().removesuffix(".md")
    if t in known:
        return known[t]
    hits = bases.get(t.split("/")[-1], [])
    return hits[0] if len(hits) == 1 else None


def pending():
    ingested = set()
    for p in (WIKI / "sources").glob("*.md"):
        raw = frontmatter(p).get("raw", "").strip('"')
        ingested.add(raw.replace("[[", "").replace("]]", "").removesuffix(".md"))
    out = []
    for d in sorted(ROOT.iterdir()):
        if d.is_dir() and not d.name.startswith(".") and d.name not in NON_PAPER_DIRS and (d / f"{d.name}.md").exists():
            if f"{d.name}/{d.name}" not in ingested:
                out.append(d.name)
    return out


def lint():
    files = all_md()
    known = {str(p.relative_to(ROOT).with_suffix("")): p for p in files}
    bases = {}
    for k, p in known.items():
        bases.setdefault(k.split("/")[-1], []).append(p)
    errs, warns, inbound = [], [], {p: 0 for p in files}
    for p in files:
        rel = p.relative_to(ROOT)
        for t in LINK.findall(p.read_text(errors="ignore")):
            tgt = resolve(t, known, bases)
            if tgt is None and (ROOT / t.strip()).is_file():
                continue  # non-markdown attachment (image, pdf)
            if tgt is None:
                if str(rel).startswith("wiki/"):
                    errs.append(f"broken link [[{t}]] in {rel}")
            elif tgt != p:
                inbound[tgt] += 1
    index_text = (WIKI / "index.md").read_text() if (WIKI / "index.md").exists() else ""
    for sub, kind in KINDS.items():
        for p in sorted((WIKI / sub).glob("*.md")):
            rel = p.relative_to(ROOT)
            fm = frontmatter(p)
            if fm.get("type") != kind:
                errs.append(f"{rel}: type must be '{kind}'")
            for k in REQ[kind]:
                if k not in fm:
                    errs.append(f"{rel}: missing frontmatter '{k}'")
            if inbound[p] == 0:
                warns.append(f"orphan (no inbound links): {rel}")
            if f"[[wiki/{sub}/{p.stem}" not in index_text:
                errs.append(f"not in wiki/index.md: {rel}")
    for name in pending():
        warns.append(f"pending ingest: {name}/{name}.md")
    for e in errs:
        print("ERROR ", e)
    for w in warns:
        print("WARN  ", w)
    print(f"{len(errs)} errors, {len(warns)} warnings")
    return 1 if errs else 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "lint"
    if cmd == "pending":
        names = pending()
        print("\n".join(names) if names else "(none)")
    else:
        sys.exit(lint())
