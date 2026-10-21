#!/usr/bin/env python3
"""Build static HTML pages (one per agent run) from the raw trajectory logs.

Reads (never modifies):  cybergym-bench/runs/**/trajectory/attempt_*.log, the sibling summary.json / output/, the wiki run pages' frontmatter,
                         the benchmark's own prompt code, and tools/viewer_annotations.json (curated per-run notes).
Writes (only):           docs/trajectories/   index.html, how-to-read.html, runs/<run-id>.html, README.md  and  docs/.nojekyll, docs/index.html

Properties: standard library only; deterministic (no timestamps in the output, so a rebuild only changes new or edited runs);
            every piece of log text is escaped; ANSI/control characters are stripped; key-like strings are redacted and the build FAILS
            if anything that looks like a real credential is still present.

Usage:  python3 tools/build_viewer.py            build everything
        python3 tools/build_viewer.py --check     build into memory and only report (no files written)
"""
import argparse, collections, glob, hashlib, html, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, "cybergym-bench", "runs")
WIKI = os.path.join(ROOT, "wiki", "syntheses")
OUT = os.path.join(ROOT, "docs", "trajectories")
RUN_AGENT = os.path.join(ROOT, "cybergym-bench", "cybergym-e2e", "scripts", "run_agent.py")
ANNOT = os.path.join(ROOT, "tools", "viewer_annotations.json")
REPO_BLOB = "https://github.com/hrshx3o5o6/cyberBenchmarking-e2e/blob/main/wiki/syntheses/"
OUT_CAP = 20000          # characters of one tool output kept on a page
THINK_CAP = 20000
GENERATOR = "build_viewer.py v1"
MODEL_ORDER = ["glm-5.3-flash", "deepseek-v4.1-flash", "qwen3.8-flash", "nemotron-3-super-120b-a12b", "kimi-k3", "minimax-m3",
               "qwen3.8-27b", "vidoc-1", "gpt-oss:120b", "gemma4"]

# ---------------------------------------------------------------- text safety
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\x1b[@-_]")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
REDACT = [  # (pattern, replacement) applied to ALL text before it reaches a page
    (re.compile(r"sk-shim-[0-9a-f]{6,}"), "[shim-key]"),
    (re.compile(r"/Users/[A-Za-z0-9._-]+"), "/Users/[user]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[email]"),
    (re.compile(r"\b74\.235\.167\.7\b"), "[vm-ip]"),
]
SECRET_PATTERNS = [  # the build FAILS if any of these survive redaction
    re.compile(r"sk-or-v1-[A-Za-z0-9]{10,}"), re.compile(r"\bhf_[A-Za-z0-9]{20,}"), re.compile(r"Bearer\s+[A-Za-z0-9_\-]{30,}"),
    re.compile(r"AKIA[0-9A-Z]{12,}"), re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), re.compile(r"ANTHROPIC_API_KEY=\S{12,}"),
]
REDACTIONS = collections.Counter()


def clean(t):
    t = _ANSI.sub("", t if isinstance(t, str) else str(t))
    t = _CTRL.sub("", t)
    for rx, rep in REDACT:
        t, n = rx.subn(rep, t)
        if n:
            REDACTIONS[rep] += n
    return t


def esc(t):
    return html.escape(clean(t))


# ---------------------------------------------------------------- parsing
def load_events(path):
    out = []
    with open(path, errors="replace") as f:
        for line in f:
            line = line.strip()
            if line.startswith("{"):
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out


def _text_of(c):
    if isinstance(c, str):
        return c
    return " ".join(x.get("text", "") for x in c if isinstance(x, dict))


def parse_claude(events):
    """-> steps, meta. Step = (kind, data). Tool calls are paired with their results."""
    steps, idx, meta = [], {}, {"init": None, "result": None, "unpaired": 0, "msgs": {}}
    for ev in events:
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init" and meta["init"] is None:
            meta["init"] = ev
        elif t == "assistant":
            m = ev.get("message", {})
            if m.get("id") and m.get("usage"):
                meta["msgs"][m["id"]] = m["usage"]
            for c in m.get("content", []):
                if c["type"] == "thinking" and c.get("thinking", "").strip():
                    steps.append(("think", c["thinking"]))
                elif c["type"] == "text" and c["text"].strip():
                    steps.append(("msg", c["text"]))
                elif c["type"] == "tool_use":
                    st = ("tool", {"name": c["name"], "inp": c["input"], "out": None, "err": False})
                    steps.append(st)
                    idx[c["id"]] = st
        elif t == "user":
            content = ev.get("message", {}).get("content")
            if isinstance(content, str):
                if content.strip():
                    steps.append(("user", content))
            elif isinstance(content, list):
                for c in content:
                    if c.get("type") == "tool_result" and c.get("tool_use_id") in idx:
                        d = idx[c["tool_use_id"]][1]
                        d["out"] = _text_of(c.get("content", ""))
                        d["err"] = bool(c.get("is_error"))
                    elif c.get("type") == "text" and c.get("text", "").strip():
                        steps.append(("user", c["text"]))
        elif t == "result":
            meta["result"] = ev
            meta["modelUsage"] = ev.get("modelUsage")
    meta["unpaired"] = sum(1 for k, d in steps if k == "tool" and d["out"] is None)
    return steps, meta


def parse_codex(events):
    steps, meta = [], {"turn": None, "gaps": 0, "dropped": 0, "unpaired": 0}
    for ev in events:
        t = ev.get("type")
        if t == "turn.completed":
            meta["turn"] = ev.get("usage")
        if t != "item.completed":
            continue
        it = ev["item"]
        k = it.get("type")
        if k == "command_execution":
            steps.append(("cmd", {"cmd": it.get("command", ""), "out": it.get("aggregated_output") or "", "exit": it.get("exit_code")}))
        elif k == "agent_message" and (it.get("text") or "").strip():
            steps.append(("msg", it["text"]))
        elif k == "reasoning" and (it.get("text") or "").strip():
            steps.append(("think", it["text"]))
        elif k == "todo_list":
            steps.append(("todo", it.get("items", [])))
        elif k == "file_change":
            steps.append(("file", it.get("changes") or it))
        elif k == "error":
            msg = it.get("message", "")
            m = re.search(r"dropped (\d+) events", msg)
            meta["gaps"] += 1
            meta["dropped"] += int(m.group(1)) if m else 0
            steps.append(("gap", msg))
    return steps, meta


# ---------------------------------------------------------------- discovery and metadata
def discover():
    seen, runs = {}, []
    for f in sorted(glob.glob(os.path.join(RUNS, "**", "trajectory", "attempt_*.log"), recursive=True)):
        h = hashlib.sha256(open(f, "rb").read()).hexdigest()
        if h in seen:
            continue
        seen[h] = f
        rd = f.split("/trajectory/")[0]
        if not os.path.exists(rd + "/summary.json"):
            continue
        s = json.load(open(rd + "/summary.json"))
        a = s["attempts"][0]
        events = load_events(f)
        agent = s.get("agent", "claude-code")
        model = None
        for ev in events:
            m = (ev.get("message") or {}).get("model") if isinstance(ev.get("message"), dict) else None
            if m and m != "<synthetic>":
                model = m
                break
            if ev.get("type") == "system" and ev.get("model"):
                model = ev["model"]
                break
        rel = os.path.relpath(f, RUNS)
        if model is None:
            m = re.search(r"agent_output/([^/]+)/(?:claude-code|codex)/", rel)
            model = m.group(1) if m else "unknown"
        model = model.split("/")[-1]
        if model == "oracle":                       # scripted control run, not a model run
            continue
        task = s["task"]
        ts = os.path.basename(rd).split("_e2e")[0].split("_patch")[0]
        runs.append(dict(path=f, rd=rd, rel=rel, sha=h, task=task, agent=agent, model=model, mode=s.get("mode", "e2e"),
                         style=s.get("prompt_style", "iterative"), stages=[a.get("stage%d" % i) for i in (1, 2, 3, 4)],
                         minutes=s.get("duration_minutes"), ts=ts, events=events, summary=s))
    runs.sort(key=lambda r: (r["task"], mdl_rank(r["model"]), r["mode"], r["agent"], r["ts"]))
    return runs


def mdl_rank(m):
    for i, k in enumerate(MODEL_ORDER):
        if m.startswith(k.split(":")[0]) or k.startswith(m):
            return i
    return len(MODEL_ORDER)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def run_id(r):
    return "--".join([slug(r["task"]), slug(r["model"]), r["agent"], r["mode"], r["ts"]])


def wiki_pages():
    pages = []
    for p in glob.glob(os.path.join(WIKI, "*", "run-*.md")):
        fm = open(p).read().split("---")[1]
        d = {}
        for l in fm.split("\n"):
            m = re.match(r"^(\w+):\s*(.*)$", l)
            if m:
                d[m.group(1)] = m.group(2).strip().strip('"')
        d["stem"] = os.path.relpath(p, WIKI)[:-3]
        pages.append(d)
    return pages


def _norm_model(m):
    m = (m or "").split(" ")[0].split("/")[-1].replace("-cloud", "")
    return m.replace("nemotron-3-super-120b-a12b", "nemotron-3-super")


def match_wiki(r, pages):
    base = _norm_model(r["model"])
    cands = [p for p in pages if p.get("task") == r["task"] and p.get("mode") == r["mode"]
             and p.get("harness", "claude-code") == r["agent"]
             and (_norm_model(p.get("model")) == base or _norm_model(p.get("model")).startswith(base) or base.startswith(_norm_model(p.get("model"))))]
    if not cands:
        return None
    mins = r["minutes"] or 0
    near = sorted([p for p in cands if abs(float(p.get("minutes") or 0) - mins) <= 0.35], key=lambda p: abs(float(p.get("minutes") or 0) - mins))
    if near:
        return near[0]
    return cands[0] if len(cands) == 1 else None


# ---------------------------------------------------------------- prompt reconstruction
_PROMPT_NS = None


def reconstruct_prompt(task, mode, style):
    global _PROMPT_NS
    if _PROMPT_NS is None:
        src = open(RUN_AGENT).read()
        i, j = src.index("def get_prompt_iterative"), src.index("def run_final_validation")
        _PROMPT_NS = {}
        exec(src[i:j], _PROMPT_NS)

    class Args:
        pass
    Args.prompt_style, Args.mode = style, mode
    repo = task.split("/")[0]
    # run_agent.py uses config["repo_to_patch"]; for these tasks it equals the project name
    return _PROMPT_NS["get_prompt"](Args, "/src/" + repo, repo)


# ---------------------------------------------------------------- html
CSS = r"""
:root{--bg:#f7f8fa;--panel:#fff;--fg:#1b2430;--muted:#5d6877;--line:#dde2ea;--accent:#2457a6;--accent-soft:#e6eefb;
--code-bg:#f0f3f7;--code-fg:#1b2430;--think-bg:#f3f1f8;--think-fg:#5a5470;--pass:#17803d;--pass-bg:#e3f4ea;--fail:#b3261e;--fail-bg:#fbe6e4;
--skip:#5d6877;--skip-bg:#eceff3;--warn:#8a5a00;--warn-bg:#fff3d6;--warn-line:#e8c66a;
--font:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#12171f;--panel:#1a212b;--fg:#e4e9f0;--muted:#9aa6b6;--line:#2b3441;--accent:#7fb0ff;--accent-soft:#1e2c44;
--code-bg:#10151c;--code-fg:#dbe3ee;--think-bg:#211f2c;--think-fg:#b4aecb;--pass:#5fd08a;--pass-bg:#16301f;--fail:#ff8f86;--fail-bg:#3a1b19;--skip:#9aa6b6;--skip-bg:#252d39;
--warn:#f0c46a;--warn-bg:#33290f;--warn-line:#6b5420;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#12171f;--panel:#1a212b;--fg:#e4e9f0;--muted:#9aa6b6;--line:#2b3441;--accent:#7fb0ff;--accent-soft:#1e2c44;
--code-bg:#10151c;--code-fg:#dbe3ee;--think-bg:#211f2c;--think-fg:#b4aecb;--pass:#5fd08a;--pass-bg:#16301f;--fail:#ff8f86;--fail-bg:#3a1b19;--skip:#9aa6b6;--skip-bg:#252d39;
--warn:#f0c46a;--warn-bg:#33290f;--warn-line:#6b5420;color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font:15px/1.55 var(--font);margin:0;padding-block:20px 56px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.wrap{max-width:940px;margin:0 auto;display:flex;flex-direction:column;gap:18px;min-width:0}
a{color:var(--accent)}h1{font-size:1.45rem;line-height:1.25;margin:0;text-wrap:balance}h2{font-size:1.05rem;margin:0 0 8px}
.crumbs{font-size:.85rem;color:var(--muted)}.sub{color:var(--muted);margin:2px 0 0;font-size:.92rem}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px 16px;min-width:0}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px 16px;margin:0}
.facts div{min-width:0}.facts dt{font-size:.75rem;color:var(--muted);margin:0}.facts dd{margin:1px 0 0;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.chips{display:flex;gap:6px;flex-wrap:wrap}.chip{font:600 .78rem var(--font);padding:2px 8px;border-radius:999px}
.chip.pass{color:var(--pass);background:var(--pass-bg)}.chip.fail{color:var(--fail);background:var(--fail-bg)}.chip.skip{color:var(--skip);background:var(--skip-bg)}
.banner{background:var(--warn-bg);border:1px solid var(--warn-line);color:var(--fg);border-radius:8px;padding:10px 14px}
.banner b{color:var(--warn)}.banner.fail{background:var(--fail-bg);border-color:var(--fail)}.banner.fail b{color:var(--fail)}
.banner.info{background:var(--accent-soft);border-color:var(--line)}.banner.info b{color:var(--accent)}
details>summary{cursor:pointer;color:var(--muted);font-size:.88rem}details[open]>summary{margin-bottom:8px}
.badge{font-size:.72rem;border:1px solid var(--line);border-radius:4px;padding:1px 6px;color:var(--muted);margin-left:6px;vertical-align:middle;font-weight:400}
pre{background:var(--code-bg);color:var(--code-fg);font:12.5px/1.5 var(--mono);padding:10px 12px;border-radius:6px;margin:0;overflow-x:auto;white-space:pre-wrap;overflow-wrap:anywhere;max-width:100%}
.steps{display:flex;flex-direction:column;gap:10px;margin:0;padding:0;list-style:none}
.step{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--line);border-radius:6px;padding:10px 14px;min-width:0}
.step.msg{border-left-color:var(--accent)}.step.cmd{border-left-color:var(--muted)}.step.think{border-left-color:var(--think-fg);background:var(--think-bg)}
.step.err{border-left-color:var(--fail)}.step.gap{border-left-color:var(--warn);background:var(--warn-bg)}.step.todo{border-left-color:var(--pass)}.step.user{border-left-color:var(--warn)}
.shead{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;font-size:.8rem;color:var(--muted);margin-bottom:6px}
.shead a{color:var(--muted);text-decoration:none;font-variant-numeric:tabular-nums}.shead .kind{font-weight:600;color:var(--fg)}
.pill{font-size:.7rem;border-radius:4px;padding:0 6px;background:var(--accent-soft);color:var(--accent);border:1px solid var(--line)}
.pill.red{background:var(--fail-bg);color:var(--fail)}.pill.amber{background:var(--warn-bg);color:var(--warn)}
.msgtext{white-space:pre-wrap;overflow-wrap:anywhere;margin:0}.thinktext{white-space:pre-wrap;overflow-wrap:anywhere;margin:0;color:var(--think-fg);font-size:.92rem}
.out{margin-top:8px}.exit{font-size:.75rem;color:var(--muted)}.exit.bad{color:var(--fail)}
.tablewrap{overflow-x:auto;max-width:100%}table{border-collapse:collapse;width:100%;font-size:.88rem;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:.75rem;color:var(--muted);font-weight:600;white-space:nowrap}
td.n{white-space:nowrap}.note{font-size:.82rem;color:var(--muted)}.jump{display:flex;gap:14px;flex-wrap:wrap;font-size:.88rem}
footer{font-size:.78rem;color:var(--muted);border-top:1px solid var(--line);padding-top:12px;overflow-wrap:anywhere}h3.task{font-size:.95rem;margin:10px 0 4px}
table.runs{table-layout:fixed;min-width:760px}table.runs td,table.runs th{overflow-wrap:anywhere}table.runs .chips{flex-wrap:nowrap}.chip{white-space:nowrap;flex:none;overflow-wrap:normal;word-break:normal}table.runs td.n{overflow-wrap:normal}
"""
HEAD = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex,nofollow"><title>@@TITLE@@</title><style>' + CSS + "</style></head><body><div class=\"wrap\">")
TAIL = "</div></body></html>"


def head(title):
    return HEAD.replace("@@TITLE@@", esc(title))
STAGE_LABEL = {"passed": ("pass", "pass"), "failed": ("fail", "fail"), "no_poc": ("fail", "no PoC"), "no_patch": ("fail", "no patch"),
               "skipped": ("skip", "skip"), "error": ("fail", "error"), None: ("skip", "-")}


def chip(s):
    k, lab = STAGE_LABEL.get(s, ("skip", str(s)))
    return '<span class="chip %s">%s</span>' % (k, esc(lab))


def truncate(t, cap):
    t = t or ""
    return (t, 0) if len(t) <= cap else (t[:cap], len(t) - cap)


def out_block(t, exit_code=None):
    t = t or ""
    short, cut = truncate(t, OUT_CAP)
    lines = (t.count("\n") + 1) if t else 0
    note = "\n[... %s more characters not shown; see the raw log]" % format(cut, ",") if cut else ""
    ex = ""
    if exit_code is not None:
        ex = ' <span class="exit%s">exit %s</span>' % (" bad" if exit_code not in (0, None) else "", esc(exit_code))
    if not t.strip():
        return '<div class="out"><span class="exit">no output</span>%s</div>' % ex
    if lines <= 10 and len(t) <= 900:
        return '<div class="out"><pre>%s%s</pre>%s</div>' % (esc(short), esc(note), ex)
    return '<details class="out"><summary>output · %s lines%s</summary><pre>%s%s</pre></details>' % (format(lines, ","), ex, esc(short), esc(note))


PILLS = [(re.compile(r"validate\.py"), "validator run", ""), (re.compile(r"/output/poc\.bin"), "PoC path", ""),
         (re.compile(r"/output/fix\.patch|apply_patch"), "patch", ""), (re.compile(r"crash-[0-9a-f]{10}"), "crash file", ""),
         (re.compile(r"seed_corpus|unzip"), "seed corpus", "amber"), (re.compile(r"/src_backup"), "backup tree", ""),
         (re.compile(r"git log|git status|git diff"), "git", ""),
         (re.compile(r"-newer\b|-newermt|--time-style|stat -c|stat -f|ls -l[a-z]*t\b|ls -lat|-mtime"), "modification times", "amber"),
         (re.compile(r"\b(curl|wget)\b|git ls-remote|pip3? install"), "network", "amber")]


def pills(cmd, out=""):
    ps = [(l, c) for rx, l, c in PILLS if rx.search(cmd or "")]
    if "rompt is too long" in (out or ""):
        ps.append(("context limit", "red"))
    return "".join('<span class="pill %s">%s</span>' % (c, esc(l)) for l, c in ps)


def render_steps(steps):
    out, n = [], 0
    for kind, d in steps:
        n += 1
        sid = "s%d" % n
        head = lambda label, extra="": '<div class="shead"><a href="#%s">#%d</a><span class="kind">%s</span>%s</div>' % (sid, n, label, extra)
        if kind == "msg":
            out.append('<li class="step msg" id="%s">%s<p class="msgtext">%s</p></li>' % (sid, head("Model message"), esc(d)))
        elif kind == "user":
            out.append('<li class="step user" id="%s">%s<p class="msgtext">%s</p></li>' % (sid, head("Message to the model (not from the tool)"), esc(truncate(d, OUT_CAP)[0])))
        elif kind == "think":
            sh, cut = truncate(d, THINK_CAP)
            extra = "\n[... %s more characters not shown]" % format(cut, ",") if cut else ""
            out.append('<li class="step think" id="%s">%s<details><summary>%s lines</summary><p class="thinktext">%s%s</p></details></li>'
                       % (sid, head("Reasoning"), d.count("\n") + 1, esc(sh), esc(extra)))
        elif kind == "cmd":
            out.append('<li class="step cmd" id="%s">%s<pre>%s</pre>%s</li>' % (sid, head("Command", pills(d["cmd"], d["out"])), esc(d["cmd"]), out_block(d["out"], d["exit"])))
        elif kind == "tool":
            inp, nm = d["inp"], d["name"]
            body = inp["command"] if nm == "Bash" and isinstance(inp, dict) and "command" in inp else json.dumps(inp, indent=1, ensure_ascii=False)
            sh, cut = truncate(body, OUT_CAP)
            res = out_block(d["out"]) if d["out"] is not None else '<div class="out"><span class="exit bad">no result recorded</span></div>'
            out.append('<li class="step cmd%s" id="%s">%s<pre>%s%s</pre>%s</li>' % (" err" if d["err"] else "", sid, head("Tool: " + esc(nm), pills(body, d["out"] or "")),
                                                                               esc(sh), "…" if cut else "", res))
        elif kind == "todo":
            items = "".join("<li>%s %s</li>" % ("☑" if i.get("completed") else "☐", esc(i.get("text", ""))) for i in d)
            out.append('<li class="step todo" id="%s">%s<ul style="margin:0;padding-left:1.1rem">%s</ul></li>' % (sid, head("To-do list"), items))
        elif kind == "file":
            out.append('<li class="step cmd" id="%s">%s<pre>%s</pre></li>' % (sid, head("File change"), esc(json.dumps(d, ensure_ascii=False)[:2000])))
        elif kind == "gap":
            out.append('<li class="step gap" id="%s">%s<p class="msgtext">%s</p></li>' % (sid, head("Log gap"), esc(d)))
    return "\n".join(out), n


def hexdump(b, n=96):
    rows = []
    for i in range(0, min(len(b), n), 16):
        ch = b[i:i + 16]
        rows.append("%04x  %s  %s" % (i, " ".join("%02x" % x for x in ch).ljust(47), "".join(chr(x) if 32 <= x < 127 else "." for x in ch)))
    return "\n".join(rows)


def load_annotations():
    return json.load(open(ANNOT)) if os.path.exists(ANNOT) else {}


def banner(a):
    cls = {"warn": "", "fail": " fail", "info": " info"}.get(a.get("level", "warn"), "")
    return '<div class="banner%s"><b>%s</b> %s</div>' % (cls, esc(a["title"]), esc(a["text"]))


def env_and_tools(r, steps, meta):
    cnt = collections.Counter()
    if r["agent"] == "codex":
        for k, d in steps:
            if k == "cmd":
                cnt["shell command"] += 1
            elif k == "file":
                cnt["file change (apply_patch)"] += 1
            elif k == "todo":
                cnt["plan / to-do update"] += 1
        env = ("<p class=\"msgtext\">Codex does not record its tool list or settings in its log, so none is shown. From what this run did, the agent had a shell, a "
               "file-patching tool and a plan/to-do tool. The benchmark starts Codex with web search disabled and approvals bypassed, inside the task container.</p>")
    else:
        for k, d in steps:
            if k == "tool":
                cnt[d["name"]] += 1
        i = meta.get("init")
        if i:
            env = ('<dl class="facts"><div><dt>Model reported by the harness</dt><dd>%s</dd></div><div><dt>Working directory</dt><dd>%s</dd></div>'
                   '<div><dt>Permission mode</dt><dd>%s</dd></div><div><dt>MCP servers</dt><dd>%d</dd></div></dl>'
                   '<p style="margin:10px 0 4px"><b>Tools available to the agent</b> (from the log\'s first record):</p><p class="msgtext">%s</p>'
                   % (esc(i.get("model", "")), esc(i.get("cwd", "")), esc(i.get("permissionMode", "")), len(i.get("mcp_servers", [])), esc(", ".join(i.get("tools", [])))))
        else:
            env = "<p class=\"msgtext\">The log has no initialisation record, so the tool list is not known.</p>"
    return env, ", ".join("%d × %s" % (v, k) for k, v in cnt.most_common()) or "none"


def token_totals(r, meta):
    n = lambda x: x if isinstance(x, (int, float)) and not isinstance(x, bool) else 0
    if r["agent"] == "codex":
        u = meta.get("turn") or {}
        cached = n(u.get("cached_input_tokens"))
        return dict(requests=None, fresh=max(0, n(u.get("input_tokens")) - cached), cache=cached, out=n(u.get("output_tokens")))
    mu = meta.get("modelUsage")
    if isinstance(mu, dict) and mu:     # per-model totals in the harness's final record; per-message usage is empty for some providers
        fresh = sum(n(v.get("inputTokens")) + n(v.get("cacheCreationInputTokens")) for v in mu.values())
        cache = sum(n(v.get("cacheReadInputTokens")) for v in mu.values())
        out = sum(n(v.get("outputTokens")) for v in mu.values())
        return dict(requests=len(meta["msgs"]), fresh=fresh, cache=cache, out=out)
    msgs = meta["msgs"]
    return dict(requests=len(msgs), fresh=sum(n(u.get("input_tokens")) for u in msgs.values()),
                cache=sum(n(u.get("cache_read_input_tokens")) for u in msgs.values()), out=sum(n(u.get("output_tokens")) for u in msgs.values()))


def build_run(r, wp, ann):
    parser = parse_codex if r["agent"] == "codex" else parse_claude
    steps, meta = parser(r["events"])
    body, nsteps = render_steps(steps)
    tools_n = sum(1 for k, d in steps if k in ("tool", "cmd"))
    problems = []
    if meta.get("unpaired"):
        problems.append("%d tool calls without a recorded result" % meta["unpaired"])
    env, used = env_and_tools(r, steps, meta)
    tk = token_totals(r, meta)
    final = ""
    for k, d in reversed(steps):
        if k == "msg":
            final = d
            break
    if not final and meta.get("result"):
        final = str(meta["result"].get("result") or "")
    out_dir = r["rd"] + "/output"
    poc = patch = None
    for pth in (out_dir + "/poc.bin", r["rd"] + "/workspace_attempt_1/output/poc.bin"):
        if os.path.exists(pth):
            poc = open(pth, "rb").read()
            break
    for pth in (out_dir + "/fix.patch", r["rd"] + "/workspace_attempt_1/output/fix.patch"):
        if os.path.exists(pth):
            patch = open(pth, errors="replace").read()
            break
    prompt = reconstruct_prompt(r["task"], r["mode"], r["style"])
    total = tk["fresh"] + tk["cache"]
    share = ("%.0f%%" % (100 * tk["cache"] / total)) if total else "n/a"
    cost = ""
    if wp:
        if wp.get("quota_mtok"):
            cost = "%.2fM quota (free allowance)" % float(wp["quota_mtok"])
        elif wp.get("cost_usd") not in (None, ""):
            cost = "$%s" % wp["cost_usd"]
    title = "%s · %s · %s" % (r["task"], r["model"], r["agent"])
    banners = "".join(banner(a) for a in ann) if ann else ""
    if meta.get("gaps"):
        banners += banner(dict(level="warn", title="Incomplete log.", text="The Codex log has %d 'event stream lagged' warnings, in which up to %d events were dropped, so part of this run is not in the record." % (meta["gaps"], meta["dropped"])))
    wl = ('<a href="%s%s.md">wiki page</a>' % (REPO_BLOB, wp["stem"])) if wp else "no matching wiki page"
    rid = run_id(r)
    h = head(title)
    h += '<div class="crumbs"><a href="../index.html">All runs</a> › %s › %s</div>' % (esc(r["task"].split("/")[0]), esc(r["agent"]))
    h += '<header><h1>%s <span class="badge">%s</span> <span class="badge">%s</span></h1><p class="sub">%s · run %s · %s</p></header>' % (
        esc(r["task"]), esc(r["agent"]), esc(r["mode"]), esc(r["model"]), esc(r["ts"]), wl)
    h += '<div class="chips" aria-label="Stage results">%s</div>' % "".join(chip(s) for s in r["stages"])
    h += banners
    h += ('<section class="panel"><dl class="facts"><div><dt>Model</dt><dd>%s</dd></div><div><dt>Harness</dt><dd>%s</dd></div><div><dt>Mode</dt><dd>%s</dd></div>'
          '<div><dt>Minutes</dt><dd>%.1f</dd></div><div><dt>Model responses</dt><dd>%s</dd></div><div><dt>Tokens (fresh / cached / output)</dt><dd>%s / %s / %s</dd></div>'
          '<div><dt>Cache share</dt><dd>%s</dd></div><div><dt>Cost</dt><dd>%s</dd></div><div><dt>Steps shown</dt><dd>%d</dd></div>'
          '<div style="grid-column:1/-1"><dt>Tools used</dt><dd>%s</dd></div></dl></section>' % (
              esc(r["model"]), esc(r["agent"]), esc(r["mode"]), r["minutes"] or 0, tk["requests"] if tk["requests"] is not None else "n/a",
              format(tk["fresh"], ","), format(tk["cache"], ","), format(tk["out"], ","), share, esc(cost or "see the wiki page"), nsteps, esc(used)))
    h += ('<nav class="jump"><a href="#prompt">Prompt</a><a href="#env">Tools &amp; environment</a><a href="#s1">First step</a><a href="#final">Final message</a>%s%s<a href="#prov">Provenance</a></nav>'
          % ('<a href="#poc">PoC</a>' if poc else "", '<a href="#patch">Patch</a>' if patch else ""))
    h += ('<details class="panel" id="prompt"><summary>Prompt given to the agent <span class="badge">reconstructed</span></summary><p class="note">Rebuilt from the benchmark\'s prompt '
          'code (unchanged since 2026-09-01) for this task, mode %s and prompt style %s, as recorded in the run\'s summary; it was not saved at run time.</p><pre>%s</pre></details>'
          % (esc(r["mode"]), esc(r["style"]), esc(prompt)))
    h += '<details class="panel" id="env"><summary>Tools &amp; environment</summary>%s</details>' % env
    h += '<section><h2>Steps</h2><ol class="steps">%s</ol></section>' % body
    h += '<section class="panel" id="final"><h2>Final message</h2><p class="msgtext">%s</p></section>' % (esc(truncate(final, OUT_CAP)[0]) if final else "(none)")
    if poc is not None:
        h += '<section class="panel" id="poc"><h2>PoC <span class="badge">%s bytes</span></h2><pre>%s</pre><p class="note">First 96 bytes.</p></section>' % (format(len(poc), ","), esc(hexdump(poc)))
    if patch:
        h += '<section class="panel" id="patch"><h2>Patch <span class="badge">%s bytes</span></h2><pre>%s</pre></section>' % (format(len(patch), ","), esc(truncate(patch, OUT_CAP)[0]))
    h += ('<footer id="prov">Source: <code>cybergym-bench/runs/%s</code> · sha256 <code>%s…</code> · %d log events · %s</footer>'
          % (esc(r["rel"]), r["sha"][:24], len(r["events"]), GENERATOR))
    h += TAIL
    return rid, h, dict(steps=nsteps, tools=tools_n, problems=problems, cost=cost, tk=tk, share=share, banners=bool(ann) or bool(meta.get("gaps")))


def build_index(rows):
    by_task = collections.OrderedDict()
    for row in rows:
        by_task.setdefault(row["r"]["task"], []).append(row)
    h = head("CyberGym-E2E run viewer")
    h += ('<header><h1>CyberGym-E2E run viewer</h1><p class="sub">One page per agent run: the prompt, every model step and tool call, and the grading outcome. '
          '%d runs across %d tasks. <a href="how-to-read.html">How to read these pages</a>.</p></header>' % (len(rows), len(by_task)))
    h += '<div class="banner info"><b>Read the Note column.</b> Some tasks leak the answer and some runs ended for reasons that say nothing about the model. Flagged runs repeat the explanation in a banner on their page.</div>'
    h += '<nav class="jump">' + "".join('<a href="#t-%s">%s</a>' % (slug(t), esc(t.split("/")[0])) for t in by_task) + "</nav>"
    for t, rs in by_task.items():
        h += '<section id="t-%s"><h3 class="task">%s</h3><div class="tablewrap"><table class="runs"><colgroup><col style="width:17%%"><col style="width:11%%"><col style="width:9%%"><col style="width:27%%"><col style="width:6%%"><col style="width:12%%"><col style="width:18%%"></colgroup><thead><tr><th>Model</th><th>Harness</th><th>Mode</th><th>S1 S2 S3 S4</th><th>Min</th><th>Cost</th><th>Note</th></tr></thead><tbody>' % (slug(t), esc(t))
        for row in rs:
            r = row["r"]
            h += ('<tr><td><a href="runs/%s.html">%s</a></td><td class="n">%s</td><td class="n">%s</td><td><div class="chips">%s</div></td><td class="n">%.1f</td><td class="n">%s</td><td>%s</td></tr>'
                  % (row["id"], esc(r["model"]), esc(r["agent"]), esc(r["mode"]), "".join(chip(s) for s in r["stages"]), r["minutes"] or 0,
                     esc(row["info"]["cost"].replace(" (free allowance)", "") or "-"), esc(row["note"])))
        h += "</tbody></table></div></section>"
    h += '<footer>Generated by %s from the raw trajectory logs. Each page links to its wiki page for the analysis. Cost is dollars for paid models and free-quota tokens for vidoc-1.</footer>' % GENERATOR
    return h + TAIL


HOWTO = """<header><h1>How to read these pages</h1><p class="sub">CyberGym-E2E agent runs, one page each.</p></header>
<section class="panel"><h2>What a run is</h2><p style="margin:0">An AI agent is given the source code of a project with a known memory-safety bug. In <b>e2e</b> mode it must find the bug, write a proof-of-concept input (PoC)
and a patch. In <b>patch-only</b> mode it is also given the crashing input and crash log, and only has to write the patch. Each page shows the whole run in order:
the prompt, the agent's reasoning, every command or tool call, and what came back.</p></section>
<section class="panel"><h2>The grading stages</h2><p style="margin:0 0 6px"><b>S1</b> the agent's PoC crashes the vulnerable build. <b>S2</b> the agent's patch stops that crash. <b>S3</b> the project's own tests still pass.
<b>S4</b> the patch also stops the benchmark's own crash input, which shows the agent found the intended bug. The paper counts S1 + S2 + S3 as success.</p>
<p style="margin:0"><b>no PoC / no patch</b>: the agent left that file missing, so grading stopped. <b>skip</b>: not graded because an earlier stage failed. In patch-only mode S1 and S2 are not part of the task and show as skip.</p></section>
<section class="panel"><h2>Reading a run page</h2><ul style="margin:0;padding-left:1.1rem"><li><b>Prompt</b> is rebuilt from the benchmark's code, not saved at run time; the page says so.</li>
<li><b>Reasoning</b> is the model's own thinking, shaded and collapsed. Long tool output is collapsed and cut at 20,000 characters; the raw log has all of it.</li>
<li><b>Pills</b> on a step mark things that matter when interpreting a run: a validator run, a PoC or patch path, a seed corpus, a crash file, modification-time checks, network use, a context-limit error.</li>
<li><b>Banners</b> at the top of a page explain a known caveat, such as a leak in the task or an incomplete log.</li>
<li>Click a step number to get a link to that step.</li></ul></section>
<section class="panel"><h2>Things that can make a result misleading</h2><ul style="margin:0;padding-left:1.1rem"><li>The files the benchmark's own fix changes carry a later modification time than the rest of the source, on most tasks checked.</li>
<li>One task ships the ground-truth PoC inside its source; another has a build script that names the bug and the fix.</li>
<li>A PoC with no patch is never run, so a saved PoC can go ungraded.</li>
<li>Some runs ended on a tool-call format failure, a context-window limit, a spending limit set by us, or an incomplete log.</li></ul>
<p class="note" style="margin:8px 0 0">The wiki's pages on each task and batch give the details.</p></section>
<footer>Pages are generated from the raw logs by tools/build_viewer.py and are static: no scripts, no external requests.</footer>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    ann_all = load_annotations()
    pages = wiki_pages()
    runs = discover()
    files, rows, report = {}, [], collections.Counter()
    unmatched, used_stems = [], set()
    for r in runs:
        wp = match_wiki(r, pages)
        if wp is None:
            unmatched.append(r["rel"])
        ann = list(ann_all.get(wp["stem"], [])) if wp else []
        if wp and wp["stem"] in ann_all:
            used_stems.add(wp["stem"])
        ann += ann_all.get("path:" + os.path.basename(r["rd"]) + ":" + r["agent"] + ":" + r["task"], [])
        rid, h, info = build_run(r, wp, ann)
        files["runs/%s.html" % rid] = h
        note = "; ".join(a["short"] for a in ann if a.get("short"))
        rows.append(dict(r=r, id=rid, info=info, note=note))
        report["pages"] += 1
        report["problems"] += len(info["problems"])
    files["index.html"] = build_index(rows)
    files["how-to-read.html"] = head("How to read these pages") + HOWTO + TAIL
    files["README.md"] = ("# Run viewer pages\n\nGenerated by `tools/build_viewer.py` from the raw trajectory logs in `cybergym-bench/runs/`. Do not edit by hand.\n\n"
                          "- `index.html`: all runs, grouped by task\n- `runs/`: one page per run\n- `how-to-read.html`: glossary\n\nRebuild: `python3 tools/build_viewer.py`.\n")
    # ---- checks that fail the build
    bad = []
    for name, content in files.items():
        for rx in SECRET_PATTERNS:
            if rx.search(content):
                bad.append((name, rx.pattern))
        if "\x1b" in content or _CTRL.search(content):
            bad.append((name, "control characters"))
    sizes = sorted(((len(c), n) for n, c in files.items()), reverse=True)
    total = sum(len(c) for c in files.values())
    print("runs discovered:", len(runs), "| pages:", report["pages"], "| files:", len(files), "| total MB: %.1f" % (total / 1e6))
    print("largest pages:", [(n, "%.1f MB" % (s / 1e6)) for s, n in sizes[:3]])
    print("redactions applied:", dict(REDACTIONS) or "none")
    print("runs without a matching wiki page:", len(unmatched), unmatched[:6])
    print("tool calls without results:", report["problems"])
    missing = sorted(set(k for k in ann_all if not k.startswith("path:")) - used_stems)
    print("curated notes: %d of %d pages found their run; not found: %s" % (len(used_stems), len([k for k in ann_all if not k.startswith("path:")]), missing))
    if bad:
        print("BUILD FAILED, credential-like or control content found:", bad[:5])
        sys.exit(1)
    if sizes[0][0] > 15_000_000:
        print("BUILD FAILED: a page is larger than 15 MB")
        sys.exit(1)
    if args.check:
        return
    os.makedirs(os.path.join(OUT, "runs"), exist_ok=True)
    wanted = set()
    for name, content in files.items():
        p = os.path.join(OUT, name)
        wanted.add(os.path.normpath(p))
        if os.path.exists(p) and open(p).read() == content:
            continue
        open(p, "w").write(content)
    for p in glob.glob(os.path.join(OUT, "runs", "*.html")):      # drop pages of runs that no longer exist
        if os.path.normpath(p) not in wanted:
            os.remove(p)
    docs = os.path.dirname(OUT)
    open(os.path.join(docs, ".nojekyll"), "w").write("")
    open(os.path.join(docs, "index.html"), "w").write('<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex"><meta http-equiv="refresh" content="0; url=trajectories/index.html"><a href="trajectories/index.html">Run viewer</a>')
    print("written to", OUT)


if __name__ == "__main__":
    main()
