# Paired-run report

Generated 2026-11-20T00:39:19Z from saved artifacts. Model calls made by this report: 0.

Counts, paired differences and traces only. With two to six issues one result moves the estimate a lot; no population-wide speed-up or significance claim. Pilot issues are development runs and are excluded from the paired table. Performance conclusions are pending the held-out study.

## pytest-dev__pytest-11143 (pilot)

Repository pytest-dev/pytest; s `b5ff089d2cc9`, t `6995257cf470`; stale packet `2a2f7e4aa881`.

Environment controls: base **ok** (unresolved, 1 FAIL_TO_PASS failing), reference patch **ok** (resolved).

| Arm | Live | Terminal state | Patch | Official grade | Outcome | Actions | Checks | Solve s |
|---|---|---|---|---|---|---:|---:|---:|
| source_only | yes | completed_patch | patch, 505 B | resolved | **resolved** | 8 | 0 | 8.4 |
| static_stale | yes | completed_patch | patch, 551 B | unresolved | **unresolved** | 4 | 0 | 13.4 |
| selective_stale | yes | completed_patch | patch, 509 B | unresolved | **unresolved** | 6 | 3 | 8.2 |

## Primary paired success (held-out issues only)

Held-out issues: 0; complete static/selective pairs: 0; both 0, neither 0, selective only 0, static only 0, missing 0; paired difference None.

Not measured in this run: full current-source rebuild; released DocAgent review-and-sync workflow; fresh-memory arms; rebuild amortisation for H=1,5,20.
