# Pilot run: pytest-dev__pytest-11143

One development pilot that validated the evaluation pipeline end to end on 2026-11-20. It is reserved
from held-out evaluation. One issue with one small local model supports no performance conclusion.

## Verdicts

| | Status | Evidence |
|---|---|---|
| Environment controls | established | Unmodified base: the designated test ran and failed (1 failed, 115 passed). Reference patch: resolved (116 passed). |
| Pipeline acceptance | accepted | Three live attempts reached a terminal state; three unedited model patches applied and were graded by the official harness; the case report replays offline with no model call. |

| Arm | Official outcome | What the patch did | Actions | Solve time |
|---|---|---|---:|---:|
| Source only | resolved | Guarded the docstring check; 116 tests passed. | 8 | 8.4 s |
| Static stale memory | unresolved | Broken indentation; the patch applied but the test run could not start. | 4 | 13.4 s |
| Selectively checked stale memory | unresolved | Changed only a type annotation; the target test still failed. | 6 (3 checks) | 8.2 s |

## Run facts

- Dataset: SWE-bench Lite, test split, revision `b0dde1093fe417d83b7184254edf8199c1f0dff5`.
- Pre-fix commit t: `6995257cf470d2143ad1683824962de4071c0eb7`. Memory commit s: `b5ff089d2cc939b042c8ad7a6a0e1850fc169907` (30.6 days earlier).
- Selection: seventh candidate in the seeded round-robin order (seed 20261119), the first that met the rule, chosen before any solver ran. See `screening/screening_log.json`.
- Evaluator: SWE-bench 5.0.1 (`87ab1f6ced28f75ba73ca899dc759b019310944a`) on a GitHub-hosted Linux runner, image `swebench/sweb.eval.x86_64.pytest-dev_1776_pytest-11143@sha256:e08ce142adec5ec985e867e910045734ec3c58fe174fc054c5f83855bed78fd4`.
- Solver: qwen3:14b (Q4_K_M) through Ollama 0.40.16 and `experiments/backends/toolloop_agent.py`; 360 s and 12 visible actions per attempt.
- Stale packet `2a2f7e4aa881…` for both memory arms; selective final packet `00ccf56ae9dc…`; none for source only.
- Driver revision at prepare time: `bf31158`. Later commits fixed report reading and cleanup and did not change solver inputs.

## What this run did not show

- The selective arm's three checks all landed on claims that were still correct. The one drifted claim
  that the issue's module contains (`K00254`) was 41st in retrieval order and stayed unchecked. Repair
  and omit behaviour is covered only by the deterministic tests in `tests/test_experiments.py`.
- That drifted claim is in the task's module but not on the code path the traceback names.
- The solver had no shell tool, so it could not run tests.
- Per-process memory was not measured; host-wide and GPU peaks are in each attempt's `summary.json`.

## Layout

```
prepared/frozen.json                    frozen manifest (see the note on paths below)
prepared/pytest-dev__pytest-11143/      issue text, the stale packet, exposed claims, drift labels
screening/                              candidate order and the seven screened candidates with decisions
runs/<instance>/<arm>/<attempt>/        summary.json, ledger.jsonl (trace), patch.diff, packets, handoff, requests
grading_requests/controls|attempts/     the requests sent to the official grader, predictions JSONL
official/controls|attempts/             the harness's report.json plus outcome.json and done.json
report/                                 summary.md, per_issue.csv, report.json
case_runs/, case_report/                the pilot trace as a case bundle and its offline report
validation/                             summary.json (three verdicts, every command and exit status), state.json
study.pilot.json, backend.json          the study and backend configuration used
```

The per-test output and harness run logs are not copied here. They are on the two grading branches,
under `grading/results/`:

- `grading/pytest-dev__pytest-11143-controls-03b3c25d-20261120t002507`
- `grading/pytest-dev__pytest-11143-attempts-03b3c25d-20261120t003216`

In this folder those two request ids are shortened to `controls` and `attempts`.

## Notes on this copy

- Machine-specific values were replaced with `<repo>`, `<temp>`, `<python>`, `<home>` and `<host>`.
  The manifest hash `03b3c25d…` recorded in the run was computed over the original `frozen.json`, so
  it does not match the redacted copy here.
- `claim_index.json` (the full 1,535-claim inventory, about 790 KB) is left out. Its hash is the
  `inventory_sha256` in the manifest and `bench.py prepare` rebuilds it.
- Files are stored byte for byte (`.gitattributes` disables line-ending conversion) so the patches
  apply as recorded.
