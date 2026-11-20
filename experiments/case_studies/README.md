# Staleness case studies (Task 1)

Collect four evidence-backed cases showing when a stored repository claim misdirects an agent, when
source inspection recovers it, and when the old claim is still useful. The cases are chosen to
explain; their frequencies say nothing about how common the problem is.

Standard library and Git only. No SWE-bench, no output from the benchmark package.

## Commands

Run from this directory.

```bash
python cases.py validate --manifest cases.json
python cases.py smoke    --backend fake
python cases.py run      --case C02 --arm both --backend-config ../backends/backend.example.json --out runs
python cases.py replay   --case C02 --runs runs --offline
python cases.py report   --runs runs --out reports
```

`replay` and `report` rebuild Markdown from saved observations. They start no backend and call no model.

## Writing a case

Copy `cases.example.json` to `cases.json`. One entry per case:

| Field | Meaning |
|---|---|
| `case_id`, `category` | `moved_owner`, `interface_drift`, `obsolete_test`, `harmless_change` |
| `repo` | `{"kind": "git", "url": ...}` or `{"kind": "fixture", "script": ...}` for a constructed fixture |
| `s`, `t` | Exact old SHA and descendant SHA |
| `claim` | `claim_id`, the exact old `statement`, `covered_path`, and a `predicate` |
| `change_origin` | `natural_commit` or `injected_fixture` |
| `note_origin` | `historical_document`, `snapshot_generated` or `researcher_authored` |
| `task` | `kind` (`localize` or `patch`) and a neutral `prompt` that does not name the answer |
| `oracle` | For `patch`: a command as an argument array and the expected exit code |

Expected answers and reviewer labels go in `cases.evaluator.json` next to the manifest. `validate`
rejects a manifest that carries them. That file is never copied into an agent workspace.

Predicates the experimental verifier understands: `signature_has_param`, `symbol_owner`,
`literal_equals`. A function that takes `**kwargs`, a duplicated definition, a missing file or a file
that does not parse gives `unresolved`, with the reason kept.

## What a run records

For each case, both arms start from the same note bytes on a clean snapshot of t, with the order
alternated by case. The checked arm records two things separately: the released helper's file-level
change signal, and the experimental verifier's verdict with its policy action (reuse, repair, omit).
Defaults are 180 s and eight visible actions per session, the check included. The oracle runs after
the agent exits, in a tree the agent never saw, with a 60 s limit. An empty patch on a patch task is
graded as a failure; a backend that cannot start is `infrastructure_missing`; a timeout is
`budget_exhausted`.

```
runs/<case>/case.json                       claim, evidence at s and t, provenance, gate result
runs/<case>/attempts/<attempt>/summary.json backend identity, packet hashes, check, oracle, timing
runs/<case>/attempts/<attempt>/ledger.jsonl run_id, seq, role, stage, event_type, claim_id, path,
                                            symbol, action, evidence, check_status, policy_action, elapsed_ms
runs/<case>/attempts/<attempt>/packet_initial.md, packet_final.md, patch.diff
```

Attempt ids are unique and earlier attempts are never overwritten. Each ledger is capped at 64 KiB
and each excerpt at 512 bytes; truncated events are counted and the terminal summary is always kept.

## Reading a report

Each report states the old claim, what changed with evidence at both revisions, a side-by-side list
of recorded actions with event numbers, the point where the arms diverged or that they converged,
and the oracle result. It says "reliance unknown" unless an action shows otherwise, and never infers
what a model believed from a failed patch. Sessions from a fake backend are flagged as zero
observations, missing sessions are listed, and a constructed change or note is labelled as not an
observed incident. The index separates what the released helper detected from what the experimental
verifier and human reviewers established.

`cases.example.json` holds one constructed fixture (`C00`) that exists only to show the schema.
