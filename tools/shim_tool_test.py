#!/usr/bin/env python3
"""Codex-style test of a model through the metering shim: a per-key budget, then a multi-turn tool-calling exchange over the Responses API
(streaming, parallel tool calls, function_call_output items), then the shim's own count of what the key used.

Environment: SHIM_MASTER_KEY (from the node's config/.env; never printed). The shim must already run for the model under test.
usage: shim_tool_test.py [--shim http://172.18.0.1:4100] [--budget 1.0] [--json out.json]
"""
import argparse, json, os, time, urllib.request

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("--shim", default="http://172.18.0.1:4100")
ap.add_argument("--budget", type=float, default=1.0)
ap.add_argument("--json", default=None)
args = ap.parse_args()
MASTER = os.environ["SHIM_MASTER_KEY"]


def call(path, body=None, key=None, stream=False, timeout=600):
    req = urllib.request.Request(args.shim + path, json.dumps(body).encode() if body is not None else None,
                                 {"authorization": "Bearer " + (key or MASTER), "content-type": "application/json"})
    r = urllib.request.urlopen(req, timeout=timeout)
    if not stream:
        return json.load(r)
    events = []
    for line in r:
        if line.startswith(b"data: ") and b"[DONE]" not in line:
            events.append(json.loads(line[6:]))
    return events


key = call("/key/generate", {"key_alias": "glm-vet", "max_budget": args.budget})["key"]
tools = [{"type": "function", "name": "shell", "description": "Run a shell command and return its output",
          "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}]
inp = [{"type": "message", "role": "user", "content": [{"type": "input_text",
        "text": "You are a coding agent. Run `echo hello` and `uname -s` with the shell tool, then tell me both outputs in one sentence."}]}]
outputs = {"echo hello": "hello", "uname -s": "Linux"}
steps, final_text = [], ""
for turn in range(1, 7):
    t0 = time.time()
    ev = call("/v1/responses", {"model": "gpt-5", "input": inp, "tools": tools, "stream": True, "store": False}, key=key, stream=True)
    calls = [e["item"] for e in ev if e.get("type") == "response.output_item.done" and (e.get("item") or {}).get("type") == "function_call"]
    msgs = [e["item"] for e in ev if e.get("type") == "response.output_item.done" and (e.get("item") or {}).get("type") == "message"]
    done = next((e for e in ev if e.get("type") == "response.completed"), {})
    usage = (done.get("response") or {}).get("usage") or {}
    ok = []
    for c in calls:
        try:
            ok.append("command" in json.loads(c["arguments"]))
        except (ValueError, KeyError):
            ok.append(False)
    text = "".join(p.get("text", "") for m in msgs for p in m.get("content", []) if p.get("type") == "output_text")
    steps.append({"turn": turn, "seconds": round(time.time() - t0, 2), "events": len(ev), "tool_calls": len(calls), "args_valid": ok, "text": text[:160],
                  "completed": bool(done), "input_tokens": usage.get("input_tokens"), "cached": (usage.get("input_tokens_details") or {}).get("cached_tokens"),
                  "output_tokens": usage.get("output_tokens")})
    if not calls:
        final_text = text
        break
    for c in calls:
        inp.append(c)
        try:
            cmd = json.loads(c["arguments"]).get("command", "")
        except ValueError:
            cmd = ""
        inp.append({"type": "function_call_output", "call_id": c["call_id"], "output": outputs.get(cmd.strip("` "), "(no output)")})
info = call("/key/info?key=" + key).get("info", {})
out = {"steps": steps, "final_mentions_both": "hello" in final_text.lower() and "linux" in final_text.lower(),
       "shim_count": {k: info.get(k) for k in ("requests", "input_tokens", "cache_read_tokens", "output_tokens", "errors", "spend")}}
print(json.dumps(out, indent=1))
if args.json:
    open(args.json, "w").write(json.dumps(out, indent=1))
