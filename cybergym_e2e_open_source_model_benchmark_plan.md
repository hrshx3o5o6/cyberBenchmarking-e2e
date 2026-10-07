# CyberGym-E2E: Open-Source Model Benchmarking Plan

## 1. Objective

The immediate goal is to benchmark a small set of open-source coding/agent models on **CyberGym-E2E**, starting with a manageable pilot of **10 tasks out of the full 920-task benchmark**.

The intended progression is:

```text
10 tasks
   ↓
inspect results + fix benchmark integration
   ↓
50 tasks
   ↓
100+ tasks
   ↓
potentially the full 920 tasks
```

The key principle is to keep the benchmark environment, agent harness, prompts, tools, task selection, time/resource budget, and evaluation procedure constant across models. The primary variable should be the **underlying LLM**.

---

# 2. What CyberGym-E2E Is

CyberGym-E2E is a benchmark for evaluating AI agents on **end-to-end real-world cybersecurity capabilities**.

The benchmark covers the vulnerability lifecycle:

```text
Vulnerability discovery
        ↓
PoC generation
        ↓
Root-cause analysis
        ↓
Patch generation
        ↓
Patch validation
        ↓
Functionality validation
```

The benchmark contains **920 real-world vulnerabilities across 139 open-source projects**.

The vulnerabilities are primarily C/C++ and are based on sanitizer-detectable memory-safety vulnerabilities sourced from OSS-Fuzz.

The benchmark is designed around three goals:

1. Realistic tasks
2. Reproducible environments
3. Scalable evaluation

A major motivation is that many existing benchmarks evaluate only one part of the vulnerability lifecycle, such as vulnerability detection or patching, rather than requiring an agent to perform the complete workflow.

---

# 3. CyberGym-E2E Task Modes

There are two important evaluation modes.

## 3.1 Patch-only mode

The agent receives:

```text
Source code
Ground-truth PoC
Crash log
```

The agent then has to understand the vulnerability and produce a patch.

This mode primarily tests:

```text
Crash
 ↓
Root-cause analysis
 ↓
Patch generation
 ↓
Validation
```

It is useful for separating the difficulty of **patching** from the difficulty of **discovering the vulnerability and constructing a PoC**.

---

## 3.2 End-to-end mode

This is the more important mode for the planned experiment.

The agent starts with essentially:

```text
Source code
Build environment
```

It must independently:

1. Explore the repository.
2. Identify a potential vulnerability.
3. Understand the vulnerable execution path.
4. Construct a proof-of-concept.
5. Run the PoC.
6. Confirm the vulnerability.
7. Diagnose the root cause.
8. Generate a patch.
9. Apply the patch.
10. Validate that the PoC no longer crashes.
11. Verify that normal functionality still works.

The agent is expected to create:

```text
/output/poc.bin
/output/fix.patch
```

The benchmark then evaluates these artifacts.

---

# 4. What the Agent's PoC Means

This is a critical concept.

The **agent's PoC** is the proof-of-concept input/artifact that the AI agent itself creates after investigating the source code.

It is NOT the benchmark's hidden/ground-truth PoC.

Conceptually:

```text
Agent investigates source
        ↓
Identifies suspected vulnerability
        ↓
Figures out what input should trigger it
        ↓
Creates poc.bin
        ↓
Runs poc.bin against vulnerable version
        ↓
Observes crash / sanitizer failure
```

The PoC therefore provides concrete evidence that the agent has actually found an executable manifestation of the vulnerability.

### Simplified example

Suppose the vulnerable code contains:

```c
void parse(char *data, size_t len) {
    char buf[16];
    memcpy(buf, data, len);
}
```

An agent may determine that an input larger than 16 bytes can trigger the vulnerability.

It could create a binary input containing something equivalent to:

```text
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
```

and save it as:

```text
/output/poc.bin
```

The agent then runs the target program with that input.

If the vulnerable build produces an AddressSanitizer crash, the agent has demonstrated that its PoC triggers a vulnerability.

The benchmark does not simply check whether the agent wrote a plausible PoC. It actually executes the PoC.

---

# 5. CyberGym-E2E Validation Stages

The benchmark uses four important validation stages.

## S1 — Agent PoC triggers the vulnerability

The agent-generated PoC is executed against the vulnerable version.

Question:

> Does the agent's `poc.bin` actually trigger the expected crash/vulnerability manifestation?

If yes:

```text
S1 = pass
```

This is the first major indication that the agent successfully discovered a vulnerability and constructed a usable PoC.

---

## S2 — Agent patch eliminates the agent PoC crash

The agent-generated patch is applied.

Then the same agent-generated PoC is executed again.

Question:

> Does the patch eliminate the crash triggered by the agent's PoC?

If yes:

```text
S2 = pass
```

---

## S3 — Functionality tests still pass

The patched project is tested using functionality tests.

Question:

> Did the agent's patch actually preserve the normal behavior/functionality of the project?

If yes:

```text
S3 = pass
```

S1–S3 form the basic end-to-end success criteria.

---

## S4 — Agent patch eliminates the ground-truth PoC

The benchmark also has the original/ground-truth PoC associated with the vulnerability.

The agent's patch is tested against that PoC.

Question:

> Does the agent's patch also eliminate the intended vulnerability manifestation represented by the benchmark's ground-truth PoC?

If yes:

```text
S4 = pass
```

S4 is particularly useful diagnostically.

---

# 6. Why S3 and S4 Can Differ

An important subtlety is:

```text
S3 > S4
```

can happen.

Imagine the benchmark's intended vulnerability is:

```text
Bug A
```

but the agent accidentally discovers and patches:

```text
Bug B
```

Its own PoC for Bug B may stop crashing, and the project may still pass its functionality tests.

Therefore:

```text
S1 = PASS
S2 = PASS
S3 = PASS
S4 = FAIL
```

is possible.

This can mean that the agent successfully found and fixed a different vulnerability or manifestation rather than the exact intended vulnerability.

Therefore:

- S3 is a core end-to-end success metric.
- S4 is valuable diagnostic information about whether the intended vulnerability was fixed.

---

# 7. Why the Agent's PoC Matters

The PoC is the bridge between **vulnerability discovery** and **evidence**.

The agent cannot merely say:

> "I think this function is vulnerable."

It has to produce something executable that demonstrates the problem.

The full reasoning loop is:

```text
Source code
    ↓
Hypothesis about vulnerability
    ↓
Locate vulnerable path
    ↓
Construct PoC
    ↓
Execute PoC
    ↓
Observe crash
    ↓
Refine understanding
    ↓
Patch
    ↓
Re-run PoC
    ↓
Validate functionality
```

This is why end-to-end vulnerability discovery is significantly harder than simply giving an agent a crash and asking it to patch the code.

---

# 8. Why Patch-Only Is Easier

In patch-only mode, the benchmark effectively gives the agent the hard starting clue:

```text
Ground-truth PoC
+
Crash log
```

The agent can work backwards:

```text
Crash
 ↓
Locate stack/function
 ↓
Trace execution
 ↓
Identify root cause
 ↓
Patch
```

In E2E mode:

```text
Source
 ↓
Where should I look?
 ↓
What is actually vulnerable?
 ↓
How can I trigger it?
 ↓
What PoC should I create?
 ↓
What caused the crash?
 ↓
How do I patch it?
```

The CyberGym-E2E results indicate that **vulnerability discovery + PoC generation is a major bottleneck**, while patch generation is substantially easier once the vulnerability is already exposed.

---

# 9. Agent Behavior That We Should Expect

The paper's trajectory analysis describes successful agents often following a pattern similar to:

```text
1. Parse vulnerability-related clues
2. Search the repository
3. Locate potentially relevant code
4. Trace the vulnerable execution path
5. Construct an initial PoC
6. Run the PoC
7. Inspect validator/crash feedback
8. Refine the PoC
9. Diagnose root cause
10. Create patch
11. Re-run validation
```

Typical exploration tools include things like:

```text
grep
ripgrep
find
source inspection
build commands
test execution
PoC execution
```

Failure modes include:

- Analysis failure
- Ineffective exploration
- Resource exhaustion
- Context exhaustion
- Premature abandonment

This matters for our experiment because a model can fail even when it has the underlying coding ability if it spends its context budget inefficiently or explores the repository poorly.

---

# 10. The Proposed Open-Source Model Set

For the initial 10-task pilot, use three open-source coding models:

## Model 1 — Qwen3-Coder-30B-A3B-Instruct

Architecture:

```text
MoE
30B total parameters
~3.3B active parameters
```

Why it is useful:

- Code-focused model.
- Designed for agentic coding/repository-scale tasks.
- Large context window.
- MoE architecture provides an interesting efficiency comparison.
- Has an OpenAI-compatible serving path through vLLM.

This should be the **first model to integrate into the benchmark harness**, because it provides a straightforward OpenAI-compatible inference endpoint.

---

## Model 2 — DeepSeek-Coder-V2-Lite-Instruct

Architecture:

```text
MoE
~16B total parameters
~2.4B active parameters
```

Why it is useful:

- Different model family from Qwen.
- Code-focused.
- Long context.
- Provides a second MoE reference point with a smaller overall model.

---

## Model 3 — Qwen2.5-Coder-32B-Instruct

Architecture:

```text
Dense
~32.5B parameters
```

Why it is useful:

- Code-focused.
- Large context.
- Dense architecture.
- Provides a useful contrast against Qwen3-Coder's MoE architecture.

The particularly interesting controlled comparison is:

```text
Qwen3-Coder
30B total / ~3.3B active / MoE

vs.

Qwen2.5-Coder
~32.5B / dense
```

This gives us a model-family/architecture comparison without making the initial experiment unnecessarily large.

---

# 11. Experimental Design

The experiment should look like:

```text
                    CyberGym-E2E
                         │
                    Same 10 tasks
                         │
                 Same agent harness
                         │
             ┌───────────┼───────────┐
             ↓           ↓           ↓
        Qwen3-Coder   DeepSeek    Qwen2.5-Coder
             │           │           │
             ↓           ↓           ↓
          S1-S4       S1-S4       S1-S4
```

The important rule:

> The model should be the main changing variable.

Do NOT accidentally compare:

```text
Model A + Agent Harness A
```

against:

```text
Model B + Agent Harness B
```

and then conclude that the models themselves differ.

That would actually be a:

```text
model + scaffold + tools + prompt
```

comparison.

For the first experiment, keep the following identical:

- CyberGym-E2E tasks
- Agent scaffold
- System prompt
- Tool set
- Tool implementations
- Time limit
- Token budget, where possible
- Retry policy
- Environment
- Docker configuration
- Network/firewall policy
- Validation procedure
- Task ordering
- Output format
- Evaluation scripts

Only swap the model endpoint.

---

# 12. Start With 10 Tasks

Do NOT immediately run:

```text
920 tasks × 3 models
```

Start with:

```text
10 tasks × 3 models
=
30 runs
```

The purpose of these first 30 runs is not to produce a statistically definitive benchmark.

It is to answer:

1. Does the integration work?
2. Can the models actually operate the CyberGym-E2E environment?
3. Are PoCs being created correctly?
4. Are patches being generated correctly?
5. Is validation working?
6. Are logs being captured?
7. Are token/cost/time measurements available?
8. What failure modes are appearing?
9. Is the agent harness itself causing failures?
10. Is the model endpoint stable?

Only after this is working should the benchmark be scaled.

---

# 13. Task Selection

Do not simply pick 10 tasks arbitrarily if the goal is to learn something meaningful from the pilot.

Try to make the initial sample contain variation in:

- Repository size
- Lines of code
- PoC complexity
- Patch size
- Vulnerability type
- Project complexity
- Build complexity

A possible conceptual split:

```text
2 relatively small/easier tasks
3 medium tasks
3 larger/more complex tasks
2 difficult/interesting tasks
```

The exact task IDs should be chosen after inspecting the CyberGym-E2E task metadata.

Most importantly:

> Use exactly the same 10 tasks for all three models.

If Model A receives one set of tasks and Model B receives another, task difficulty becomes a confounding variable.

---

# 14. Metrics to Record

For every model/task run, record at minimum:

```text
Model
Task ID

S1
S2
S3
S4

Wall-clock time
LLM request count
Input tokens
Output tokens

Failure reason
```

A useful result table is:

| Model | Patch-only | S1 | S2 | S3 | S4 |
|---|---:|---:|---:|---:|---:|
| Qwen3-Coder | ... | ... | ... | ... | ... |
| DeepSeek-Coder | ... | ... | ... | ... | ... |
| Qwen2.5-Coder | ... | ... | ... | ... | ... |

For the 10-task pilot, also keep per-task results.

Example:

| Task | Model | S1 | S2 | S3 | S4 | Time | Requests | Failure |
|---|---|---:|---:|---:|---:|---:|---:|---|
| task-1 | Qwen3 | ✓ | ✓ | ✓ | ✗ | ... | ... | ... |
| task-1 | DeepSeek | ✓ | ✗ | - | - | ... | ... | ... |
| task-1 | Qwen2.5 | ✗ | - | - | - | ... | ... | ... |

The `-` values mean later stages were not reached.

---

# 15. Resource Measurements

Because these are local/open-source models, record model-serving resource usage as well.

Potential measurements:

```text
GPU model
GPU memory
Peak VRAM
Inference throughput
Tokens/sec
Wall-clock time
CPU usage
System RAM
Number of model requests
Input tokens
Output tokens
```

If inference is performed remotely, record:

```text
endpoint
model version
quantization
GPU configuration
```

The exact hardware configuration must remain constant across model comparisons where possible.

---

# 16. E2E vs Patch-Only for the Pilot

The initial focus should be **E2E mode** because it measures the full capability we are interested in.

The primary pipeline is:

```text
Source
 ↓
Discovery
 ↓
PoC generation
 ↓
PoC execution
 ↓
Root-cause analysis
 ↓
Patch
 ↓
PoC validation
 ↓
Functionality validation
```

However, patch-only mode can be extremely useful as a secondary experiment.

Suppose:

```text
Model A:
E2E S3 = 10%

Patch-only = 70%
```

That tells us that the model may be capable of patching once the vulnerability is exposed, but struggles with discovery/PoC generation.

Conversely, if both are poor, the bottleneck may be more general.

Therefore:

### Initial priority

```text
E2E
```

### Secondary diagnostic experiment

```text
Patch-only
```

---

# 17. Local Model Serving Architecture

The clean architecture should be:

```text
CyberGym-E2E runner
        │
        ▼
Agent harness
        │
        ▼
OpenAI-compatible API
        │
        ▼
vLLM
        │
        ▼
Open-source model
```

For example:

```text
run_agent.py
      │
      │ OpenAI-compatible request
      ▼
http://localhost:8000/v1
      │
      ▼
vLLM
      │
      ▼
Qwen3-Coder-30B-A3B-Instruct
```

This is preferable to modifying the CyberGym agent logic separately for every model.

The benchmark should ideally just see:

```text
MODEL_ENDPOINT
MODEL_NAME
```

and everything else stays the same.

---

# 18. First Integration Target

The first model to integrate should be:

```text
Qwen3-Coder-30B-A3B-Instruct
```

The immediate engineering task is to inspect CyberGym-E2E's:

```text
scripts/run_agent.py
```

and determine:

1. How the model is initialized.
2. Which API/client is used.
3. How the system prompt is constructed.
4. What tools are exposed.
5. How tool calls are handled.
6. How many turns are allowed.
7. How timeouts work.
8. How retries work.
9. Where logs are stored.
10. How outputs are collected.
11. How the model endpoint can be replaced.
12. Whether the code already supports OpenAI-compatible endpoints.
13. Whether any assumptions are hardcoded around Anthropic/OpenAI models.

Do not start modifying the benchmark blindly.

First understand the existing execution path.

---

# 19. Official CyberGym-E2E Setup

The official repository provides the benchmark runner and task data.

Repository:

https://github.com/sunblaze-ucb/cybergym-e2e

The documented setup includes dependencies such as:

```bash
pip install tomli tomli_w anthropic openai boto3 httpx huggingface_hub docker
```

The benchmark data can be downloaded using the Hugging Face CLI.

The repository also provides Docker images and a firewall mechanism.

The benchmark runner supports commands conceptually like:

```bash
python scripts/run_agent.py curl/arvo_66012 --mode e2e
```

and:

```bash
python scripts/run_agent.py curl/arvo_66012 --mode patch-only
```

Batch execution is supported through the provided batch script.

The benchmark uses a network isolation/firewall mechanism. This should be preserved during experiments so that network access does not become an uncontrolled source of information or a confounding variable.

---

# 20. Network Isolation

This is important for reproducibility.

The benchmark's firewall restricts agent network access and is intended to allow only necessary LLM API access.

For a local model, the architecture should ideally be:

```text
Agent container
     │
     ├── benchmark environment
     │
     └── local/private LLM endpoint
```

The agent should not be able to freely browse the internet.

Otherwise, the model could potentially retrieve information about the project/vulnerability externally, which would change what is being measured.

Therefore:

> Keep the network configuration identical across all three models.

---

# 21. The Main Scientific Question

The experiment should ultimately answer something like:

> How well can different open-source coding models autonomously perform the complete CyberGym-E2E vulnerability discovery, PoC generation, patching, and validation workflow under the same agent scaffold and resource constraints?

This is much more meaningful than simply asking:

> Which model writes better code?

CyberGym-E2E is testing an **agentic software-engineering/security workflow**, not just code generation.

---

# 22. What We Should NOT Do Yet

Avoid these until the basic experiment works:

### Do not run all 920 tasks immediately

It will make debugging expensive.

### Do not use different agent scaffolds

Otherwise model comparison becomes confounded.

### Do not give one model extra tools

Unless the experiment is explicitly intended to compare tool configurations.

### Do not change prompts per model

At least not in the initial controlled comparison.

### Do not disable the benchmark's network restrictions

Unless there is a deliberate experimental reason.

### Do not judge models based on one or two successful tasks

The first 10-task run is a pilot, not a definitive benchmark.

### Do not optimize the agent around a particular model

The initial goal is a controlled model comparison.

---

# 23. Recommended Experimental Progression

## Phase 0 — Understand the harness

Inspect:

```text
scripts/run_agent.py
scripts/batch_run.sh
task metadata
validation code
model/client configuration
```

Understand exactly how an existing model goes from:

```text
task
 ↓
agent
 ↓
tools
 ↓
PoC
 ↓
patch
 ↓
validator
```

---

## Phase 1 — One task, one model

Run:

```text
Qwen3-Coder
+
one CyberGym-E2E task
```

Verify:

- Model responds correctly.
- Tool calls work.
- Repository can be explored.
- Agent can build/run commands.
- `/output/poc.bin` is produced.
- `/output/fix.patch` is produced.
- Validator runs.
- Logs are captured.
- S1–S4 are correctly recorded.

Do not scale until this works.

---

## Phase 2 — 10 tasks × 3 models

Run:

```text
3 models
×
10 identical tasks
=
30 runs
```

Collect:

```text
S1
S2
S3
S4
time
tokens
requests
failure reasons
```

Then inspect trajectories manually.

---

## Phase 3 — Failure analysis

Group failures into categories such as:

```text
Discovery failure
PoC-generation failure
PoC-execution failure
Root-cause-analysis failure
Patch failure
Functionality regression
Context exhaustion
Timeout
Build/environment failure
Agent abandonment
```

This is arguably more informative than a single aggregate success percentage.

---

## Phase 4 — 50 tasks

If the harness is stable:

```text
3 × 50 = 150 runs
```

At this point the aggregate S1–S4 measurements become more informative.

---

## Phase 5 — 100–200 tasks

Expand if:

- The task pipeline is stable.
- Model serving is stable.
- Results are not dominated by infrastructure failures.
- Logging is reliable.
- The experimental configuration is frozen.

---

# 24. Important Interpretation Framework

When looking at results, don't only look at:

```text
S3 = 25%
```

Break down where the model loses tasks.

For example:

```text
100 tasks
   ↓
70 S1
   ↓
55 S2
   ↓
48 S3
   ↓
20 S4
```

This tells us:

```text
Discovery/PoC:
30 tasks lost

Patch:
15 tasks lost

Functionality:
7 tasks lost

Intended-vulnerability correctness:
28 tasks lost relative to S3
```

That gives us an actual picture of the agent's weaknesses.

---

# 25. The Core Conceptual Model

Keep this mental model throughout the experiment:

```text
                 CYBERGYM-E2E
                       │
                       ▼
                  Repository
                       │
                       ▼
              ┌─────────────────┐
              │ Agent explores  │
              └────────┬────────┘
                       │
                       ▼
                Finds hypothesis
                       │
                       ▼
                 Creates PoC
                       │
                       ▼
                 Runs PoC
                       │
                 ┌─────┴─────┐
                 │           │
               FAIL         PASS
                 │           │
             refine         S1
                 │           │
                 └─────┬─────┘
                       ▼
                 Root-cause
                   analysis
                       │
                       ▼
                  fix.patch
                       │
                       ▼
                    S2
                       │
                       ▼
              Functionality tests
                       │
                       ▼
                    S3
                       │
                       ▼
            Ground-truth PoC test
                       │
                       ▼
                    S4
```

The **agent-generated PoC** is therefore not a side artifact. It is one of the central outputs of the E2E task.

---

# 26. Immediate Next Steps

The recommended immediate workflow is:

```text
STEP 1
Inspect CyberGym-E2E repository

        ↓

STEP 2
Read scripts/run_agent.py carefully

        ↓

STEP 3
Understand current model/client abstraction

        ↓

STEP 4
Determine how to point it at a local
OpenAI-compatible vLLM endpoint

        ↓

STEP 5
Serve Qwen3-Coder-30B-A3B-Instruct

        ↓

STEP 6
Run ONE E2E task

        ↓

STEP 7
Verify PoC + patch + S1-S4

        ↓

STEP 8
Run the same task again if necessary
to debug infrastructure

        ↓

STEP 9
Run 10 selected tasks

        ↓

STEP 10
Run the same 10 tasks on DeepSeek-Coder
and Qwen2.5-Coder

        ↓

STEP 11
Analyze S1-S4 + resource usage + failures

        ↓

STEP 12
Expand to 50 tasks
```

---

# 27. Key Takeaway

The experiment is not simply:

```text
3 models
↓
which one writes the best patch?
```

It is:

```text
Can an open-source model operate as an autonomous
security/code agent through the entire lifecycle?

        source code
            ↓
       vulnerability
        discovery
            ↓
        PoC creation
            ↓
       PoC execution
            ↓
       root-cause analysis
            ↓
        patch creation
            ↓
        patch testing
            ↓
    functionality testing
```

For the first controlled experiment:

```text
Models:
1. Qwen3-Coder-30B-A3B-Instruct
2. DeepSeek-Coder-V2-Lite-Instruct
3. Qwen2.5-Coder-32B-Instruct

Tasks:
10 identical CyberGym-E2E E2E tasks

Runs:
30 total

Primary metrics:
S1, S2, S3, S4

Secondary metrics:
time, tokens, requests, infrastructure/resource usage,
and failure categories
```

The first engineering priority is **not model optimization**. It is getting one model to reliably execute one CyberGym-E2E task through the complete pipeline with correct artifact generation and validation.

Once that works, scaling the experiment becomes straightforward.
