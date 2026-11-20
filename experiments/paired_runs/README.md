# Paired issue-resolution benchmark (Task 2)

Does a selective check of stale, task-relevant memory improve test-based patch resolution within a
fixed budget? This package owns its issues, memory construction, checker, workspaces, grading requests
and analysis. A clean checkout plus public benchmark data is enough; it needs nothing from the
case-study package.

## Commands

Run from this directory, or give the path to `bench.py`.

```bash
python bench.py smoke   --backend fake
python bench.py prepare --config study.json --out OUT/prepared
python bench.py pilot   --config study.json --backend backend.json --out OUT/prepared
python bench.py run     --manifest OUT/prepared/frozen.json --backend backend.json --resume --batch
python bench.py grade   --manifest OUT/prepared/frozen.json --workers 1 --instance-id ID [--controls] [--push] [--wait-s N]
python bench.py report  --manifest OUT/prepared/frozen.json --out OUT/report
```

- `prepare` pins the dataset revision, publishes the seeded candidate order (`candidates.json`),
  screens candidates in round-robin order (`screening_log.json`, exclusions with reasons, router misses
  included), and freezes `frozen.json`. `--instance-id ID --status pilot` prepares one named issue.
- `pilot` runs the three arms on the single pilot issue and records cell times in `pilot_timing.json`.
- `run` runs held-out issues. More than one issue needs `--batch`. Nothing starts in the background.
- `grade` is per instance and uses one worker. `--controls` sends the base and reference-patch controls.
- `report` reads saved files only and makes no model call.

## Arms

| Arm | Context given to planner and implementer |
|---|---|
| `source_only` | Issue text and the pre-fix source. No generated claim or metadata; the workspace holds no generated file. |
| `static_stale` | The routed packet built from the older commit s, byte for byte. |
| `selective_stale` | Starts from the identical bytes. Up to three suspect claims, in retrieval order, are checked against the source at t: supported claims are kept, a contradicted claim is rewritten only from one unambiguous current definition, anything else is omitted with a pointer. Unchecked claims are marked. |

One allowance per attempt covers checker, planner and implementer: by default 360 s and 12 visible
actions (each check counts as one). The planner is read-only with two actions and a 600-byte handoff.
The memory bound is five documents and 8,000 UTF-8 bytes; bytes are recorded as bytes because the
backend has no tokenizer access. Arm order within an issue is fixed by the seed.

## Data and leak controls

- `t` is the benchmark's pre-fix commit; `s` is the nearest first-parent ancestor at least 30 days older.
- Snapshots are raw committed blobs of one tree: no history, no refs, no later objects.
- The memory builder sees only the tree at s. It records Python signatures and literal module
  defaults; skipped predicate types and skipped files are listed in `claim_index.json`.
- Routing uses the released helper on a small routing repository (source at s, memory anchored there,
  source at t), so its file-change signal fires on the committed s..t change.
- The reference patch, test patch, eval script and hints are dropped when the dataset is fetched; only
  their hashes are kept. Test-name lists and relevance annotations stay in the grader store.

## Files (the public interface)

```
OUT/prepared/frozen.json                 manifest: revisions, hashes, limits, arm order, driver facts
OUT/prepared/<id>/issue.md               issue text given to the solver
OUT/prepared/<id>/packet.md              the one stale packet (exact bytes)   packet.json: router metadata
OUT/prepared/<id>/claims_exposed.json    claim id, text, path, symbol, predicate, evidence revision
OUT/prepared/<id>/drift.json             evaluator-side labels for claims whose file changed
OUT/runs/<id>/<arm>/<attempt>/summary.json   terminal state, packet hashes, checks, usage, resources
OUT/runs/<id>/<arm>/<attempt>/ledger.jsonl   compact trace, 64 KiB cap, terminal counters kept
OUT/runs/<id>/<arm>/<attempt>/patch.diff     the actual diff, never edited
OUT/grading_requests/<request>/          request.json and official predictions JSONL
GRADER_STORE/results/<request>/          harness report.json, test output, outcome.json, done.json
OUT/report/summary.md, per_issue.csv, report.json
```

Resume key: manifest hash, instance, arm, solver configuration hash, seed, attempt. A terminal attempt
is never rerun; an interrupted one is kept and a new attempt id is issued. Changing the model or limits
for an issue is refused unless every arm is rerun with `--new-block`.

## Outputs and their denominators

`report.json` separates patch generation, patch application and grading. It gives the paired
static/selective table over held-out issues (pilot issues are excluded), exploration counts until the
first evaluator-annotated relevant source, planner/implementer read overlap, outdated-claim counts and
checking cost. Missing outcomes, missing annotations and zero denominators are shown as such.
Not measured by this package yet: fresh-memory arms, the released review-and-sync workflow, and full
rebuild amortisation.
