---
type: concept
created: 2026-09-30
updated: 2026-09-30
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [agents, feedback]
aliases: [fresh-context retry]
---
# Cross-run feedback

After a failed attempt, start a *fresh* run whose context contains a trajectory summary, artifact analysis, and targeted feedback on why validation failed ([[wiki/sources/cybergym-e2e]], §4.4, Table 7).

- End-to-end S3 on first-attempt failures: Opus 4.5 34.1 → 41.2 (+7.1); Sonnet 4.5 10.6 → 15.4 (+4.8).
- Authors: gain comes from feedback content, not retry variance; unguided second attempts repeat the same mistakes.
- Only one feedback iteration tested (cost).

## Related
[[wiki/concepts/agent-harness-design-effects]]
