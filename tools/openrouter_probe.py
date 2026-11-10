#!/usr/bin/env python3
"""Probe one OpenRouter model pinned to one provider: key and credit limit, the provider that answered, tool calls over several turns,
and the prompt-cache share of a growing agent-style conversation. Direct calls to OpenRouter (no shim), cost a few cents.

The key comes from the environment (OPENROUTER_API_KEY) and is never printed.
usage: openrouter_probe.py auth | tools | cache [--turns 10]   [--model z-ai/glm-5.3-flash] [--provider z-ai] [--json out.json]
  auth   GET /key (label, credit limit, usage so far) and one tiny completion: which provider and model answered, tokens, cost
  tools  a four-step tool-calling exchange: are the arguments valid JSON, does the model use the results
  cache  system prompt about 6k tokens, then each turn appends a tool call and a ~700-word tool result: cached tokens per turn, provider per turn
"""
import argparse, json, os, random, time, urllib.error, urllib.request

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("cmd", choices=["auth", "tools", "cache"])
ap.add_argument("--model", default="z-ai/glm-5.3-flash")
ap.add_argument("--provider", default="z-ai")
ap.add_argument("--turns", type=int, default=10)
ap.add_argument("--json", default=None)
args = ap.parse_args()
KEY = os.environ["OPENROUTER_API_KEY"]
BASE = "https://openrouter.ai/api/v1"
WORDS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]
TOOLS = [{"type": "function", "function": {"name": "run_shell", "description": "Run a shell command and return its output",
          "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}}]


def http(path, body=None, timeout=300):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode() if body is not None else None,
                                 {"authorization": "Bearer " + KEY, "content-type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r), round(time.time() - t0, 2)
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:400]}, round(time.time() - t0, 2)


def chat(messages, max_tokens=600, tools=None):
    body = {"model": args.model, "messages": messages, "max_tokens": max_tokens, "usage": {"include": True},
            "provider": {"order": [args.provider], "allow_fallbacks": False}}
    if tools:
        body["tools"], body["tool_choice"] = tools, "auto"
    return http("/chat/completions", body)


def usage_row(j):
    u = j.get("usage") or {}
    return {"provider": j.get("provider"), "model": j.get("model"), "prompt": u.get("prompt_tokens"), "completion": u.get("completion_tokens"),
            "cached": (u.get("prompt_tokens_details") or {}).get("cached_tokens"), "reasoning": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "cost": u.get("cost")}


def words(n, seed):
    r = random.Random(seed)
    return " ".join(r.choice(WORDS) + str(r.randint(0, 99999)) for _ in range(n))


out = {"cmd": args.cmd, "model": args.model, "provider_pin": args.provider}
if args.cmd == "auth":
    code, j, _ = http("/key")
    d = (j.get("data") or {}) if code == 200 else {}
    out["key"] = {"http": code, **{k: d.get(k) for k in ("limit", "limit_remaining", "usage", "is_free_tier") if k in d}}
    code, j, secs = chat([{"role": "user", "content": "Reply with the single word: ok"}], max_tokens=300)
    out["completion"] = {"http": code, "seconds": secs, "text": ((j.get("choices") or [{}])[0].get("message") or {}).get("content"), **(usage_row(j) if code == 200 else j)}
elif args.cmd == "tools":
    msgs = [{"role": "system", "content": "You are a coding agent. Use the run_shell tool to run commands, then report."},
            {"role": "user", "content": "Run `echo hello`, then `uname -s`, then tell me both outputs in one sentence."}]
    steps, results = [], {"echo hello": "hello", "uname -s": "Linux"}
    for turn in range(1, 7):
        code, j, secs = chat(msgs, max_tokens=1500, tools=TOOLS)
        if code != 200:
            steps.append({"turn": turn, "http": code, "error": j}); break
        m = j["choices"][0]["message"]; calls = m.get("tool_calls") or []; ok_args = []
        for c in calls:
            try:
                a = json.loads(c["function"]["arguments"]); ok_args.append(isinstance(a, dict) and "command" in a)
            except ValueError:
                ok_args.append(False)
        steps.append({"turn": turn, "seconds": secs, "tool_calls": len(calls), "args_valid": ok_args, "finish": j["choices"][0].get("finish_reason"),
                      "text": (m.get("content") or "")[:160], **usage_row(j)})
        if not calls:
            break
        msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": calls})
        for c in calls:
            try:
                cmd = json.loads(c["function"]["arguments"]).get("command", "")
            except ValueError:
                cmd = ""
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": results.get(cmd.strip("` "), "(no output)")})
    final = steps[-1].get("text", "") if steps else ""
    out["steps"] = steps
    out["verdict"] = {"final_mentions_both": "hello" in final.lower() and "linux" in final.lower(), "all_args_valid": all(all(s.get("args_valid", [True])) for s in steps)}
else:
    msgs = [{"role": "system", "content": "You are a coding agent working in a repository. Reference notes follow.\n" + words(960, 7)}]
    rows = []
    for t in range(1, args.turns + 1):
        code, j, secs = chat(msgs + [{"role": "user", "content": f"Step {t}: say 'noted' and nothing else."}], max_tokens=400, tools=TOOLS)
        if code != 200:
            rows.append({"turn": t, "http": code, "error": j}); break
        r = usage_row(j); r.update({"turn": t, "seconds": secs, "share": round((r["cached"] or 0) / r["prompt"], 3) if r["prompt"] else None})
        rows.append(r)
        cid = f"call_{t}"
        msgs += [{"role": "user", "content": f"Step {t}: say 'noted' and nothing else."},
                 {"role": "assistant", "content": "", "tool_calls": [{"id": cid, "type": "function", "function": {"name": "run_shell", "arguments": json.dumps({"command": f"cat notes_{t}.txt"})}}]},
                 {"role": "tool", "tool_call_id": cid, "content": words(700, 100 + t)}]
    out["turns"] = rows
    ok = [r for r in rows if r.get("prompt")]
    if ok:
        later = [r for r in ok if r["turn"] >= 2]
        out["summary"] = {"providers": sorted({r["provider"] for r in ok if r["provider"]}),
                          "cache_share_turn2_on": round(sum(r["cached"] or 0 for r in later) / max(1, sum(r["prompt"] for r in later)), 3) if later else None,
                          "cost_total": round(sum(r["cost"] or 0 for r in ok), 5)}
print(json.dumps(out, indent=1))
if args.json:
    open(args.json, "w").write(json.dumps(out, indent=1))
