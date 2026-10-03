---
type: concept
created: 2026-09-30
updated: 2026-09-30
sources: ["[[sources/cybergym-e2e]]"]
tags: [benchmark, pipeline]
aliases: [CyberGym-E2E pipeline]
---
# Benchmark construction pipeline

Agent-enhanced, mostly automated conversion of historical OSS-Fuzz vulnerabilities into agent environments ([[wiki/sources/cybergym-e2e]], §3.3).

1. Find patch commit by binary-searching history near the fix date; drop uninformative/multi-issue commits (~1,400 left, about half filtered).
2. Rebuild vulnerable + patched builds, verify PoC triggers only on vulnerable (~1,200 left; drop if vulnerable commit >10 commits back).
3. Code agent finds/builds/runs developer tests in Docker (~800 left).
4. Human expert validates test logs & coverage (74% accepted → initial 615 tasks; pipeline later scaled to 920 / 139 projects).

Legacy toolchain trick: reproduce on old OS (e.g. Ubuntu 16.04), then migrate artifact to newer OS (agent tooling needs GLIBC > 2.28) while keeping PoC valid.

Bottleneck: human coverage validation; future work = LLVM coverage analysis.

## Related
[[wiki/concepts/end-to-end-vulnerability-lifecycle-evaluation]] · [[wiki/entities/oss-fuzz]] · [[wiki/entities/arvo]]
