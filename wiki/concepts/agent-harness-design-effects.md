---
type: concept
created: 2026-09-30
updated: 2026-09-30
sources: ["[[sources/cybergym-e2e]]"]
tags: [agents, harness]
aliases: [harness comparison]
---
# Agent harness design effects

Same task, different harness → different cost and success ([[wiki/sources/cybergym-e2e]], §4.3, Table 5).

| Harness | File strategy | Task tracking |
|---|---|---|
| Claude Code | targeted (grep/rg) | active todo list |
| OpenHands | full-file reads | inactive |
| Codex | targeted | inactive |
| Gemini CLI | targeted | inactive |

- Sonnet 4.5: Claude Code S3 10.6% vs OpenHands 5.4% (P-O 77.4 vs 68.9). OpenHands burns context on full-file reads → fewer steps of exploration and higher cost.
- Author claim: todo tracking prevents redundant reads (from log analysis, not an ablation).

## Related
[[wiki/entities/openhands]]
