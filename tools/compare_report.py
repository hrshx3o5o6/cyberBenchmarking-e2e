"""HTML for the page that compares the DeepSeek V4.1 Flash run and the GLM 5.3 Flash run of the same 100 CyberGym-E2E tasks. Reads the tables written by compare_runs.py
(wiki/syntheses/aws-vm-data/compare-deepseek-glm/compare.json, per_task_pair.csv). Reuses the chart helpers of deepseek100_report. Static output, no scripts.
build(C, pairs, links_ds, links_glm, ctx) -> html.
"""
import csv, json, os
import deepseek100_report as base
from deepseek100_report import bars, table, sec, fmt_d


def load(d):
    return json.load(open(os.path.join(d, "compare.json"))), list(csv.DictReader(open(os.path.join(d, "per_task_pair.csv"))))


def _chip(outcome, ctx):
    cls = {"PASS S1-S4": "pass", "S4 fail": "pass"}.get(outcome, "skip" if outcome.startswith(("void", "not", "interrupted")) else "fail")
    return '<span class="chip %s">%s</span>' % (cls, ctx["esc"](outcome))


def build(C, pairs, links_ds, links_glm, ctx):
    esc = ctx["esc"]
    P, G, O = C["prefix"], C["glm51"], C["own"]
    d, g = P["deepseek"], P["glm"]; n = P["tasks"]
    ag = P["agree_s1s3"]; a4 = P["agree_s1s4"]
    rd, rg = C["runs"]["deepseek"], C["runs"]["glm"]
    out = [ctx["head"]("DeepSeek V4.1 Flash against GLM 5.3 Flash")]
    out.append('<div class="crumbs"><a href="index.html">Run viewer</a> › DeepSeek V4.1 Flash against GLM 5.3 Flash</div>')
    out.append('<header><h1>DeepSeek V4.1 Flash against GLM 5.3 Flash <span class="badge">comparison</span></h1><p class="sub">The same 100 CyberGym-E2E tasks in the same order, end to end, Codex 0.118.0, one attempt per task, 90 minutes of agent time, 10 USD cap. '
               'Reports of the two runs: <a href="deepseek-100-report.html">DeepSeek</a> · <a href="glm-100-report.html">GLM</a>.</p></header>')
    out.append('<nav class="jump"><a href="#read">Read this first</a><a href="#glance">At a glance</a><a href="#outcomes">Outcomes</a><a href="#agree">Task by task</a><a href="#cost">Time and cost</a><a href="#behaviour">Model behaviour</a><a href="#runs">The two runs</a><a href="#bigger">Other sets</a><a href="#differences">What differs</a><a href="#tasks">Per task</a><a href="#caveats">Caveats</a></nav>')
    out.append(sec("Read this first", "<p>The GLM run was stopped after 5 h 23 min (a credit guard, then the account ran out of credit), so only 51 of its 100 tasks have a valid result, and those are biased towards tasks that end early. "
                   "A fair comparison therefore uses <b>the first %d tasks of the shared dispatch order</b> (up to <code>%s</code>): every one of them has a valid GLM result, and they were picked by when they started, not by how they ended. "
                   "DeepSeek's result on the same %d tasks is set against GLM's. All headline numbers below are for this set unless a heading says otherwise; the larger sets are in <a href=\"#bigger\">Other sets</a>.</p>"
                   "<p class=\"note\">%d tasks is a small sample and each model had one attempt per task: differences of a few tasks are noise (the 95%% intervals below show how wide). The two runs also differ in more than the model (price lists, grading path, container limits, node setup, day); see <a href=\"#differences\">What differs</a>.</p>" % (C["n_prefix"], esc(C["prefix_last"]), n, n), "read"))
    sg = lambda s, k: "%d of %d (%.0f%%, 95%% interval %.0f to %.0f%%)" % (s[k], s["n"], s[k + "_pct"], s[k + "_ci"][0], s[k + "_ci"][1])
    facts = [("Passed S1 to S3 (the paper's rule)", sg(d, "s1s3"), sg(g, "s1s3")), ("Passed all four stages", sg(d, "s1s4"), sg(g, "s1s4")),
             ("Agent time, mean / median", "%.0f / %.0f min" % (d["agent_min"]["mean"], d["agent_min"]["median"]), "%.0f / %.0f min" % (g["agent_min"]["mean"], g["agent_min"]["median"])),
             ("At the 90-minute limit", "%d of %d (%.0f%%)" % (d["at_limit"], n, 100 * d["at_limit"] / n), "%d of %d (%.0f%%)" % (g["at_limit"], n, 100 * g["at_limit"] / n)),
             ("Cost per task at each run's own prices", "$%.2f (total $%.2f)" % (d["spend"]["mean"], d["spend"]["total"]), "$%.2f (total $%.2f)" % (g["spend"]["mean"], g["spend"]["total"])),
             ("Cost per task at one price list (DeepSeek's)", "$%.2f" % d["cost_per_task_at_common_price"], "$%.2f" % g["cost_per_task_at_common_price"]),
             ("Model calls per task", "%.0f" % d["tokens"]["calls_per_task"], "%.0f" % g["tokens"]["calls_per_task"]),
             ("Prompt tokens per call / output tokens per call", "%s / %s" % (fmt_d(d["tokens"]["prompt_per_call"]), d["tokens"]["out_per_call"]), "%s / %s" % (fmt_d(g["tokens"]["prompt_per_call"]), g["tokens"]["out_per_call"])),
             ("Cached share of prompt tokens", "%.1f%%" % d["tokens"]["cached_share"], "%.1f%%" % g["tokens"]["cached_share"])]
    out.append(sec("At a glance (first %d tasks)" % n, table(["", "DeepSeek V4.1 Flash", "GLM 5.3 Flash"], [[a, b, c] for a, b, c in facts]) +
                   "<p><b>DeepSeek solved more of the same tasks.</b> On S1 to S3 it passed %d against GLM's %d; the intervals overlap only partly, and the task-by-task counts below give an exact sign test of p = %.3f (%d tasks only DeepSeek solved, %d only GLM). GLM used about <b>%.1f times as many model calls</b> per task with <b>%.1f times longer prompts</b> and cached nearly all of them, so it cost about %.0f%% more at one price list even though its list prices are lower.</p>" % (
                       d["s1s3"], g["s1s3"], ag["sign_test_p"], ag["deepseek_only"], ag["glm_only"], g["tokens"]["calls_per_task"] / d["tokens"]["calls_per_task"], g["tokens"]["prompt_per_call"] / d["tokens"]["prompt_per_call"],
                       100 * (g["cost_per_task_at_common_price"] / d["cost_per_task_at_common_price"] - 1)), "glance"))
    order = ["PASS S1-S4", "S4 fail", "S2 fail", "S1 fail", "no PoC", "no patch"]
    cols = {"PASS S1-S4": "var(--pass)", "S4 fail": "var(--accent)", "S2 fail": "var(--skip)", "S1 fail": "var(--skip)", "no PoC": "var(--fail)", "no patch": "#c27a00"}
    funnel_lab = ["S1 PoC crashes the vulnerable build", "S2 patch stops that crash", "S3 other checks", "S4 intended bug fixed"]
    out.append(sec("Outcomes", "<h3 class=\"task\">DeepSeek V4.1 Flash</h3>" + bars([(k, d["outcomes"].get(k, 0), cols[k]) for k in order], label_w=120) +
                   "<h3 class=\"task\">GLM 5.3 Flash</h3>" + bars([(k, g["outcomes"].get(k, 0), cols[k]) for k in order], label_w=120) +
                   "<h3 class=\"task\">Stage funnel (tasks that passed each stage)</h3>" + table(["Stage", "DeepSeek", "GLM"], [[funnel_lab[i], str(d["funnel"][i]), str(g["funnel"][i])] for i in range(4)]) +
                   "<p class=\"note\"><b>The failures look different.</b> The harness records <i>no patch</i> when the agent never wrote <code>fix.patch</code> and <i>no PoC</i> when there is a patch but no PoC file. DeepSeek's failures are mostly <b>no PoC (%d of %d)</b>: it wrote a patch but could not produce a crashing input. GLM's are mostly <b>no patch (%d of %d)</b>: it ran out its time without a patch (whether it had a PoC is not recorded for those tasks, because grading is skipped), and %d more failed S1, meaning its PoC did not crash the vulnerable build. DeepSeek has one S1 failure.</p>" % (
                       d["outcomes"].get("no PoC", 0), n, g["outcomes"].get("no patch", 0), n, g["outcomes"].get("S1 fail", 0)), "outcomes"))
    out.append(sec("Task by task", table(["S1 to S3 on the same %d tasks" % n, "Tasks"], [["both models solved", str(ag["both"])], ["only DeepSeek solved", str(ag["deepseek_only"])], ["only GLM solved", str(ag["glm_only"])], ["neither solved", str(ag["neither"])]]) +
                   "<p>Exact sign test on the %d tasks where exactly one model solved: two-sided p = %.3f. For all four stages: both %d, only DeepSeek %d, only GLM %d (p = %.3f; very few tasks pass S4 at all, so this is weak evidence).</p>" % (ag["deepseek_only"] + ag["glm_only"], ag["sign_test_p"], a4["both"], a4["deepseek_only"], a4["glm_only"], a4["sign_test_p"]) +
                   "<p class=\"note\">The two models mostly fail on the same tasks (%d of %d tasks unsolved by both), so the difference sits in about %d tasks. The per-task table at the bottom lists every task with both outcomes.</p>" % (ag["neither"], n, ag["deepseek_only"] + ag["glm_only"]), "agree"))
    out.append(sec("Time and cost", table(["", "DeepSeek", "GLM"], [
        ["Agent minutes, mean (median)", "%.0f (%.0f)" % (d["agent_min"]["mean"], d["agent_min"]["median"]), "%.0f (%.0f)" % (g["agent_min"]["mean"], g["agent_min"]["median"])],
        ["Tasks at the 90-minute limit", "%d of %d" % (d["at_limit"], n), "%d of %d" % (g["at_limit"], n)],
        ["Graded tasks (a patch and a PoC existed)", str(d["graded"]), str(g["graded"])],
        ["Time outside the agent for graded tasks, mean (median), minutes", "%.0f (%.0f), standard grading" % (d["grading_overhead_min"]["mean"], d["grading_overhead_min"]["median"]), "%.0f (%.0f), setup A grading" % (g["grading_overhead_min"]["mean"], g["grading_overhead_min"]["median"])],
        ["Cost, total / per task / per passing task (S1 to S4), own prices", "$%.2f / $%.2f / $%.2f" % (d["spend"]["total"], d["spend"]["mean"], d["spend_pass"]), "$%.2f / $%.2f / $%.2f" % (g["spend"]["total"], g["spend"]["mean"], g["spend_pass"])],
        ["The same tokens priced at DeepSeek's list (0.30 / 0.03 / 1.20 per million), total / per task", "$%.2f / $%.2f" % (d["cost_at_common_price"], d["cost_per_task_at_common_price"]), "$%.2f / $%.2f" % (g["cost_at_common_price"], g["cost_per_task_at_common_price"])]]) +
        "<p><b>Prices.</b> DeepSeek's are an assumed Vertex rate (0.30 fresh / 0.03 cached / 1.20 output USD per million tokens, from aggregator listings, not confirmed on Google's page); GLM's are OpenRouter's list for the Z.AI endpoint (0.15 / 0.03 / 0.50). Priced at one list the cost reflects tokens only: GLM used %s prompt tokens per task against DeepSeek's %s million, and wrote %s thousand output tokens per task against %s.</p>" % (
            "%.1f million" % g["tokens"]["prompt_tokens_per_task_m"], "%.1f" % d["tokens"]["prompt_tokens_per_task_m"], "%.0f" % g["tokens"]["out_tokens_per_task_k"], "%.0f" % d["tokens"]["out_tokens_per_task_k"]) +
        "<p class=\"note\">Neither run came near the 10 USD cap. A passing task is cheap in both runs; most of the money goes to tasks that run the whole 90 minutes without a result.</p>", "cost"))
    fz = C["fuzzers"]
    out.append(sec("Model behaviour", table(["", "DeepSeek", "GLM"], [
        ["Model calls per task (usage count)", "%.0f" % d["tokens"]["calls_per_task"], "%.0f" % g["tokens"]["calls_per_task"]],
        ["Prompt tokens per call, mean", fmt_d(d["tokens"]["prompt_per_call"]), fmt_d(g["tokens"]["prompt_per_call"])],
        ["Output tokens per call, mean", str(d["tokens"]["out_per_call"]), str(g["tokens"]["out_per_call"])],
        ["Cached share of prompt tokens", "%.1f%%" % d["tokens"]["cached_share"], "%.1f%%" % g["tokens"]["cached_share"]],
        ["Call latency, median / 90th / 99th percentile (seconds)", " / ".join(str(x) for x in rd["secs"]) + " (all nodes)", " / ".join(str(x) for x in rg["secs"]) + " (head's shim only)"],
        ["Provider errors", "%d HTTP 502 of %s calls (%.1f%%), %d failed streams" % (rd["http_error"], fmt_d(rd["calls"]), 100 * rd["http_error"] / rd["calls"], rd["failed_streams"]), "%d HTTP 402 of %s head calls (credit and in-flight limits, last minutes only), %d failed streams" % (rg["http_error"], fmt_d(rg["calls"]), rg["failed_streams"])],
        ["Calls over the stall mark", "%d over 590 s (a 600-second per-call cap applied)" % rd["over_590"], "%d over 120 s; two ran to the 131,072-token output maximum (no per-call cap)" % rg["over_120"]],
        ["Agents that ran a fuzzer (all valid tasks of the run)", "%d of %d (%d with parallel workers or AFL)" % (fz["deepseek"]["ran_fuzzer"], fz["deepseek"]["tasks"], fz["deepseek"]["ran_parallel_or_afl"]), "%d of %d (%d with parallel workers or AFL)" % (fz["glm"]["ran_fuzzer"], fz["glm"]["tasks"], fz["glm"]["ran_parallel_or_afl"])],
        ["Agents that ran the task's own <code>validate.py</code> (mean runs per task)", "%d of %d (%.1f)" % (C["self_validation"]["deepseek"]["tasks_that_ran_validate_py"], fz["deepseek"]["tasks"], C["self_validation"]["deepseek"]["mean_per_task"]), "%d of %d (%.1f)" % (C["self_validation"]["glm"]["tasks_that_ran_validate_py"], fz["glm"]["tasks"], C["self_validation"]["glm"]["mean_per_task"])]]) +
        "<p class=\"note\">GLM works in many more, shorter steps (about %.0f calls per task against %.0f, with half the output per call) on prompts nearly twice as long; Z.AI caches the whole growing prompt (%.0f%% cached) while Vertex's cache covered about %.0f%%. The median call is shorter for GLM (%.1f s on the head) than for DeepSeek (%.1f s), but GLM makes many more of them.</p>" % (
            g["tokens"]["calls_per_task"], d["tokens"]["calls_per_task"], g["tokens"]["cached_share"], d["tokens"]["cached_share"], rg["secs"][0], rd["secs"][0]), "behaviour"))
    nodes = lambda r: ", ".join("%s %.0f GB" % (k, v["mem_max"]) for k, v in r["nodes"].items())
    out.append(sec("The two runs, as runs", table(["", "DeepSeek V4.1 Flash", "GLM 5.3 Flash"], [
        ["Dates (UTC)", "2026-11-04 06:07 to 17:00 (one pass; an earlier pass lost 68 tasks to memory)", "2026-11-10 08:09 to 13:32 (the third of four starts; see the GLM report)"],
        ["Wall time", "10 h 54 min", "5 h 23 min, then stopped"],
        ["Tasks with a valid result", "%d of 100 (1 stopped in grading)" % rd["graded"], "%d of 100 (3 void, %d killed in progress, %d never started)" % (rg["graded"], rg["interrupted"], rg["not_started"])],
        ["Task hours (valid tasks): agent / outside the agent", "%.0f / %.0f" % (rd["task_hours"]["agent"], rd["task_hours"]["outside_agent"]), "%.0f / %.0f" % (rg["task_hours"]["agent"], rg["task_hours"]["outside_agent"])],
        ["Spend of the valid tasks at own prices", "$%.2f" % rd["spend"], "$%.2f" % rg["spend"]],
        ["Highest memory seen on a node", nodes(rd), nodes(rg)],
        ["Largest single container", "%.1f GB (no limit set)" % rd["top_container"][0], "%.1f GB (cap 40 GB)" % rg["top_container"][0]],
        ["What stopped or hurt the run", "nothing in the final pass; the first pass ran out of memory at 10 slots per node", "a runaway container (attempt 1), an empty account (attempt 2), a credit guard that killed 16 running tasks (attempt 3)"]]), "runs"))
    og, od = O["glm"], O["deepseek"]
    out.append(sec("Other sets", table(["Set", "Tasks", "DeepSeek passed S1 to S3", "GLM passed S1 to S3", "DeepSeek S1 to S4", "GLM S1 to S4"], [
        ["First %d of the dispatch order (the fair set)" % n, str(n), "%d (%.0f%%)" % (d["s1s3"], d["s1s3_pct"]), "%d (%.0f%%)" % (g["s1s3"], g["s1s3_pct"]), str(d["s1s4"]), str(g["s1s4"])],
        ["All 51 valid GLM tasks (biased towards early finishers)", "51", "%d (%.0f%%)" % (G["deepseek"]["s1s3"], G["deepseek"]["s1s3_pct"]), "%d (%.0f%%)" % (G["glm"]["s1s3"], G["glm"]["s1s3_pct"]), str(G["deepseek"]["s1s4"]), str(G["glm"]["s1s4"])],
        ["Each run on its own valid tasks (DeepSeek 99, GLM 51)", "99 / 51", "%d (%.0f%%)" % (od["s1s3"], od["s1s3_pct"]), "%d (%.0f%%)" % (og["s1s3"], og["s1s3_pct"]), str(od["s1s4"]), str(og["s1s4"])]]) +
        "<p class=\"note\">On the 51 tasks DeepSeek solved %d against GLM's %d (sign test p = %.3f, %d only DeepSeek, %d only GLM): the same direction as in the fair set. The third row compares different task sets and is shown for completeness only.</p>" % (G["deepseek"]["s1s3"], G["glm"]["s1s3"], G["agree_s1s3"]["sign_test_p"], G["agree_s1s3"]["deepseek_only"], G["agree_s1s3"]["glm_only"]), "bigger"))
    out.append(sec("What differs between the runs (what limits the comparison)", table(["", "DeepSeek run", "GLM run"], [
        ["Model and provider", "<code>deepseek-v4.1-flash</code> on Google Vertex (managed)", "<code>glm-5.3-flash</code> on OpenRouter, pinned to Z.AI (fp8), fallbacks off"],
        ["Shim limits per call", "180 s of silence and 600 s in total", "none"],
        ["Prices used", "assumed 0.30 / 0.03 / 1.20 per million", "OpenRouter list 0.15 / 0.03 / 0.50 per million"],
        ["Grading", "standard (four containers, four builds)", "setup A (shared images): identical statuses on 13 test inputs"],
        ["Container limits", "none", "40 GB and 2,048 processes per container; janitor"],
        ["apt source", "the default Ubuntu archive", "the AWS regional mirror (the default archive was slow that day)"],
        ["Nodes and slots", "head 4 + 2 workers of 6 (m7i.4xlarge)", "the same"],
        ["Same", "tasks and order, Codex 0.118.0, 1 attempt, 90 minutes, 10 USD cap, iterative prompt, harness commit d0ae0f0", "the same"]]) +
        "<p class=\"note\">None of the differences in the lower rows should change what an agent can do in 90 minutes, but they are not proven to be neutral; the model and provider differences cannot be separated from the model itself.</p>", "differences"))
    ptab = []
    for r in pairs:
        t = r["task"]
        a = ('<a href="%s">%s</a>' % (links_ds[t], esc(t))) if t in links_ds else esc(t)
        gl = ('<a href="%s">GLM</a>' % links_glm[t]) if t in links_glm and r["glm_outcome"] not in ("void (cut off)",) else ""
        gm = r["glm_agent_min"] and "%.0f" % float(r["glm_agent_min"]) or "-"
        gs = r["glm_spend"] and "$%.2f" % float(r["glm_spend"]) or "-"
        ds_m = r["deepseek_agent_min"] and "%.0f" % float(r["deepseek_agent_min"]) or "-"
        ds_s = r["deepseek_spend"] and "$%.2f" % float(r["deepseek_spend"]) or "-"
        ptab.append("<tr><td class=\"n\">%s</td><td>%s</td><td>%s</td><td>%s</td><td class=\"n\">%s</td><td class=\"n\">%s</td><td class=\"n\">%s</td><td class=\"n\">%s</td><td>%s</td></tr>" % (
            r["position"], a, _chip(r["deepseek_outcome"], ctx), _chip(r["glm_outcome"], ctx), ds_m, gm, ds_s, gs, ("fair set · " if r["in_fair_prefix"] == "True" else "") + gl))
    out.append(sec("Per task (100, in dispatch order)", "<p class=\"note\">Outcome chips: green = passed S1 to S3 (S1 to S4 is labelled <i>PASS</i>, an S4 failure <i>S4 fail</i>); red = failed or nothing produced; grey = no result (GLM tasks void, killed in progress or never started). The fair set is the first %d rows. Links open the task's full run in the viewer.</p>" % n +
                   '<div class="tablewrap"><table class="runs"><thead><tr><th>#</th><th>Task (DeepSeek run)</th><th>DeepSeek</th><th>GLM</th><th>DS agent min</th><th>GLM agent min</th><th>DS cost</th><th>GLM cost</th><th>Notes</th></tr></thead><tbody>%s</tbody></table></div>' % "".join(ptab), "tasks"))
    out.append(sec("Caveats", "<ul style=\"margin:0;padding-left:1.1rem\"><li><b>One attempt per task, small n.</b> %d tasks; the intervals are wide and a few tasks can swap the result. Re-running either model could move its numbers.</li>"
                   "<li><b>Not a model ranking.</b> The runs differ in provider, price list, grading path, container limits and day (section above). The GLM run had provider-side problems (credit limits) that were not the model's.</li>"
                   "<li><b>Selection:</b> the fair set was chosen by dispatch order; the 51-task set favours tasks that finish early; the third row of <i>Other sets</i> mixes task sets.</li>"
                   "<li><b>Costs:</b> DeepSeek's price is assumed; GLM's is a list price. Per-task spend for both is the shim's own count of tokens times the price.</li>"
                   "<li><b>Per-call figures for GLM</b> are from the head's shim only (the workers' logs were lost with the workers).</li>"
                   "<li><b>The leak task</b> <code>qpdf/oss-fuzz_42535152</code> (ground-truth PoC inside the source tree) is in the set for both models.</li></ul>" % n, "caveats"))
    out.append('<footer>Generated by tools/compare_runs.py and tools/compare_report.py from the two runs\' result tables; deterministic, static, no scripts.</footer>')
    out.append(ctx["TAIL"])
    return "".join(out)
