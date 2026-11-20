# Case PILOT-pytest-dev-pytest-11143: benchmark_pilot

Project: https://github.com/pytest-dev/pytest  
Old revision s: `b5ff089d2cc939b042c8ad7a6a0e1850fc169907`  
Current revision t: `6995257cf470d2143ad1683824962de4071c0eb7`  
Provenance: change_origin = **natural_commit**, note_origin = **snapshot_generated**

> This is not an observed incident of stale documentation: the change, the note, or both were constructed.

## The stored claim

`K00254`: signature `_pytest.assertion.rewrite.AssertionRewriter.visit_NamedExpr(self, name: namedExpr)` (source `src/_pytest/assertion/rewrite.py`)

## What changed

| Revision | Verdict | Evidence |
|---|---|---|
| s `b5ff089d2cc9` | supported | `src/_pytest/assertion/rewrite.py` recorded by the issue-blind builder from the source at s: signature `_pytest.assertion.rewrite.AssertionRewriter.visit_NamedExpr(self, name: namedExpr)` |
| t `6995257cf470` | contradicted | `src/_pytest/assertion/rewrite.py` line 944: def AssertionRewriter.visit_NamedExpr(self, name: ast.NamedExpr) |

Who established what:

- Released DocAgent helper (file-level only): covered file changed between s and t = **True** ['src/_pytest/assertion/rewrite.py']. This is a reason to inspect the claim, not a verdict on it.
- Experimental verifier (`experimental-claim-checker-1`): the verdicts in the table above.
- Human review: {"note": "development pilot; reused only to test integration, reserved from held-out evaluation", "status": "pending"}

## Sessions

| Arm | Attempt | Live agent | Backend / model | Initial packet | Final packet | Terminal state | Oracle |
|---|---|---|---|---|---|---|---|
| checked | `pytest-dev__pytest-11143__selective_stale__seed20261119__a01` | yes | ollama-qwen3-14b-toolloop / qwen3:14b | `2a2f7e4aa881` | `00ccf56ae9dc` | completed_patch | fail (official SWE-bench harness) |
| source_only | `pytest-dev__pytest-11143__source_only__seed20261119__a01` | yes | ollama-qwen3-14b-toolloop / qwen3:14b | `None` | `None` | completed_patch | pass (official SWE-bench harness) |
| blind | `pytest-dev__pytest-11143__static_stale__seed20261119__a01` | yes | ollama-qwen3-14b-toolloop / qwen3:14b | `2a2f7e4aa881` | `2a2f7e4aa881` | completed_patch | fail (official SWE-bench harness) |

## Side by side

| Step | source_only | blind | checked |
|---|---|---|---|
| 1 | #1 source_read search | #2 source_read search | #2 check K00226 supported -> reuse |
| 2 | #2 source_read testcases/基线/代理策略/SOCKS二级代理迭代二/在线用户/在线用户更新/上线用户 | #3 source_read src/_pytest/assertion/rewrite.py | #3 check K00227 supported -> reuse |
| 3 | #3 handoff | #4 handoff | #4 check K00228 supported -> reuse |
| 4 | #4 source_read search | #5 source_edit src/_pytest/assertion/rewrite.py | #5 checks_skipped 57 claims |
| 5 | #5 source_read search | #6 source_edit src/_pytest/assertion/rewrite.py | #6 source_read search |
| 6 | #6 source_read src/_pytest/assertion/ | #7 terminal_answer | #7 source_read src/_pytest/assertion/rewrite.py |
| 7 | #7 source_read src/_pytest/assertion/rewrite.py | #8 oracle_outcome fail | #8 handoff |
| 8 | #8 source_read src/_pytest/pytester.py |  | #9 source_edit src/_pytest/assertion/rewrite.py |
| 9 | #9 source_edit src/_pytest/assertion/rewrite.py |  | #10 terminal_answer |
| 10 | #10 terminal_answer |  | #11 oracle_outcome fail |
| 11 | #11 oracle_outcome pass |  |  |

The arms diverged at agent source action 4: blind did `('source_edit', 'src/_pytest/assertion/rewrite.py')`, checked did `nothing further`.

## What each session did and what the oracle found

- **checked** (`pytest-dev__pytest-11143__selective_stale__seed20261119__a01`, ledger `attempts/pytest-dev__pytest-11143__selective_stale__seed20261119__a01/ledger.jsonl`): the agent accessed the claimed path `src/_pytest/assertion/rewrite.py` at event(s) [7, 9]; whether it relied on the note is **unknown**. Terminal answer at event 10: "Changed the parameter type of is_rewrite_disabled from str to object in src/_pytest/assertion/rewrite.py.". Patch: 509 bytes. Oracle at event 11: **fail** (official SWE-bench harness report, request pytest-dev__pytest-11143-attempts-03b3c25d-20261120t003216: resolved=False). Trace truncated: False.
- **source_only** (`pytest-dev__pytest-11143__source_only__seed20261119__a01`, ledger `attempts/pytest-dev__pytest-11143__source_only__seed20261119__a01/ledger.jsonl`): no stored note was given to this session; it accessed `src/_pytest/assertion/rewrite.py` at event(s) [7, 9]. Terminal answer at event 10: "Fixed the issue by modifying the 'is_rewrite_disabled' method to handle cases where 'docstring' might be an integer.". Patch: 505 bytes. Oracle at event 11: **pass** (official SWE-bench harness report, request pytest-dev__pytest-11143-attempts-03b3c25d-20261120t003216: resolved=True). Trace truncated: False.
- **blind** (`pytest-dev__pytest-11143__static_stale__seed20261119__a01`, ledger `attempts/pytest-dev__pytest-11143__static_stale__seed20261119__a01/ledger.jsonl`): the agent accessed the claimed path `src/_pytest/assertion/rewrite.py` at event(s) [3, 5, 6]; whether it relied on the note is **unknown**. Terminal answer at event 7: "Fixed the issue by modifying the 'is_rewrite_disabled' function to handle non-string docstring inputs.". Patch: 551 bytes. Oracle at event 8: **fail** (official SWE-bench harness report, request pytest-dev__pytest-11143-attempts-03b3c25d-20261120t003216: resolved=False; the patch applied but the test run produced no parseable results). Trace truncated: False.

All attempts on disk for this case: pytest-dev__pytest-11143__selective_stale__seed20261119__a01, pytest-dev__pytest-11143__source_only__seed20261119__a01, pytest-dev__pytest-11143__static_stale__seed20261119__a01.

A failed patch is not evidence of what the model believed; this report states only recorded actions.
