# Task 1 · Collect and replay four DocAgent staleness cases

## Assignment for Claude Code

Implement an independent case-collection and replay package under `experiments/case_studies/`. Two people must be able to run it from a fresh checkout using this brief alone. Deliver four evidence-backed case reports showing when a stored repository claim misdirects an agent, when source inspection recovers it, and when the original claim remains useful. The case set is selected for explanation; its frequencies cannot estimate field prevalence. Use small Git snapshots, a targeted local oracle and a compact event log. No SWE-bench installation or output from another team is needed.

**Starting point.** Work from [DocAgent v0.14.2 at cfd5224](https://github.com/xiangruiSun/DocAgent/tree/cfd5224729c8b2eb7502e51934aa2a2a38501357). Record the actual source SHA and your driver revision. Inspect `skills/docagent/scripts/docagent.py`, especially `context_bundle`, and `scripts/demo.py`. The released router produces ranked metadata and file-level freshness findings. Read the selected bodies to assemble the packet. A changed file is a reason to inspect a claim. A receipt or a Git anchor records review history; it cannot establish what an API currently does.

**Backend contract.** The developer can use Claude Code or any coding assistant to implement this brief. The *experimental agent* is separately configurable. Support one real backend chosen by the pair, plus a deterministic fake for smoke tests. Expose a neutral adapter callable or an external command that consumes a request JSON path and emits event JSONL, a result JSON and any patch. A CLI such as Claude Code, an agent using a GPT API, or a local coding model driven by a small tool loop can all satisfy this boundary. A text-completion endpoint needs a tool loop or equivalent file-edit interface. Avoid implementing multiple vendor SDKs just to demonstrate portability. Launch commands as argument arrays. Receive provider credentials through the environment and store only a redacted configuration. A fake or replay can test the recorder and the adapter but contributes zero agent observations.

| Request fields | Response and capability fields |
|---|---|
| schema_version, run_id, workspace, issue_text, role, prompt/context paths, time and action limits, optional model ID/seed | status, actual backend/agent/model/version, observed tool events, elapsed_ms, usage when exposed, diff path or explicit no_patch, exit_reason |
| capabilities declared at preflight | can_reset_session, can_limit_time, can_count_actions, can_capture_diff, observable_reads, usage_source; unknown values are null |

Allow any CPU/GPU, OS or remote inference endpoint. Record host, CPU, system RAM, GPU/VRAM when present, OS, backend location and model quantization if known. A hosted API moves inference off the local PC; report local peak memory and leave remote memory unknown. Count provider-reported input/output/cache separately and document cache semantics. Never substitute a heuristic token estimate for measured usage. For a backend with hidden operations, mark affected metrics unavailable. Capture observable file/tool events and short responses, excluding private reasoning, credentials and bulk transcripts.

## Divide the work

| Owner | First implementation | Data ownership | Handoff inside this pair |
|---|---|---|---|
| A · cases and ground truth | Define the case manifest, revision exporter and oracle; supply one sample packet immediately | Find and verify cases 1 and 2, preserving evidence from both revisions | Give B just the documented input schema and a tiny constructed example on day one |
| B · agent runs and reporting | Implement the adapter, packet renderer, trace validator and Markdown report generator against the example | Find and verify cases 3 and 4 | Run the paired sessions; both people cross-review the other person’s evidence |

Either person can author a manifest against the schema before the runner exists. Use the pinned released DocAgent helper directly; keep any case-only verifier in this directory. No imports from a benchmark branch, shared service, GPU queue or team database.

## Which four cases to collect

| Case | Eligibility and useful task prompt | Decisive evidence |
|---|---|---|
| 1. Moved owner | Old note points to a module/symbol that previously owned behavior. At the later revision it moved or delegates through a surviving wrapper. Ask the agent to locate or make a small change to that behavior without naming the answer. | Show old implementation, current definition or delegation, first file the agent inspects/edits, and an oracle checking the effective implementation. A passing path-existence check does not identify the owner. |
| 2. Interface/config drift | An old keyword, default, config key or method no longer has the claimed effect. A candidate is urllib3’s removal of `Retry(method_whitelist=...)`. Freeze exact revisions and inspect both; distinguish an accepted deprecated alias from an actually removed argument. | Old call/config works at s; targeted check at t demonstrates rejection or changed behavior. An agent that uses the current interface without checking is also a valid observation. |
| 3. Obsolete test procedure | A documented test selector, directory or command previously exercised a target and now misses it. Ask the agent to validate a narrow change with existing tests. | Save invocation, exit code, collection count and relevant node IDs at both revisions. A missing selector, collection error, and a successful run that exercised only unrelated tests require distinct labels. |
| 4. Harmless source change | A covered file changes while the precise stored claim stays correct. A comment-only change is an acceptable controlled fallback. | The original claim passes the same scoped check at s and t. Record whether the agent retains it, spends time confirming it or needlessly discards it. |

Search bounded Git history, changelogs, deprecations and test renames in projects such as urllib3 and pytest. The upstream deprecation and removal records are leads, not collected cases. Prefer at least two natural cases from different projects. Timebox each search to 15 minutes. If a natural case cannot be verified, create a clearly labeled controlled fixture and disclose the substitution. Record **two separate provenance fields**: change_origin = natural_commit or injected_fixture; note_origin = historical_document, snapshot_generated or researcher_authored. A true historical API change can be paired with a constructed note, but it cannot be described as an observed incident of stale documentation. [urllib3 change history](https://urllib3.readthedocs.io/en/stable/changelog.html) · [pytest migration history](https://docs.pytest.org/en/stable/changelog.html) · [pytest exit codes](https://docs.pytest.org/en/stable/reference/exit-codes.html)

## Implementation sequence

1. Create a versioned case manifest with case ID/category, project URL, old SHA s and descendant SHA t, source paths and symbols at both revisions, claim ID and exact old statement, note provenance, neutral task prompt, and oracle command/expected observation. For synthetic fixtures commit the two small states or provide a deterministic script recreating both. Store evaluator-only labels and expected answers outside the agent workspace.
2. Verify that the old claim was supported at s. Use a path, AST, static configuration or focused executable check appropriate to the actual statement. At t independently label supported, contradicted or unresolved. Record an excerpt and path/line or command result. An AST signature proves only its encoded call shape. If dynamic dispatch or fixture setup makes the result ambiguous, retain that limitation explicitly. A second member reviews the label without seeing the first member’s verdict.
3. Build two matched inputs on a clean t snapshot. **Blind reuse** injects the old packet as written. **Checked reuse** starts with that exact packet, calls the released file-level gate where applicable, and checks the suspect predicate against current evidence. Reuse supported claims; repair unique, directly evidenced facts; omit unresolved assertions and offer the original source pointer. Record the released gate result separately from the case-only checker result. Verifiers must operate on source or documented test inputs; never read the reviewer verdict or expected fix.
4. For each case run both arms with the same agent, model, tools, prompt, time/action ceiling and host class. Alternate which arm runs first. Reset workspace and session each time. Give both the same source access and allow ordinary source recovery. The agent may return a file/symbol answer, an executed validation command or a patch, according to the frozen task. No solution, later Git history, reviewer notes or hidden oracle in its workspace. If the agent ignores the note, record that outcome.
5. Run the local oracle independently after agent exit, on the submitted patch if applicable. Save short stdout/stderr, collection count if relevant, exit code and verdict. No patch is valid for a localization-only task if the hand-in includes the requested evidence. For a repair task, grade an empty patch explicitly. Failure to start the environment is infrastructure_missing; a model timeout is budget_exhausted. Preserve both.
6. Render one short report per case. Write the original claim, what changed, the side-by-side moment when actions diverged or converged, what each agent did next, and what the oracle found. Cite event sequence numbers and source SHAs. If no observation establishes reliance, label it unknown. Do not infer a model’s beliefs from a failed patch.

### Trace and disk contract

Use one JSONL event at a time: run_id, seq, role, stage, event_type, claim_id, path/symbol, observable action, short evidence, check_status, policy_action, elapsed_ms. Include exact old/new text for repairs, hashes of both starting packets, plus runtime and token counts when available. Record events for claim exposure, check, documented source read/command/edit, terminal answer and oracle outcome. A reviewer should be able to follow each report using the compact log and two source excerpts.

Example of a **synthetic schema example**, never a reportable observation:
```json
{"run_id":"C02-checked","seq":3,"stage":"verify","claim_id":"retry.keyword","event_type":"check","check_status":"contradicted","policy_action":"omit","evidence":"recorded keyword absent from current constructor signature"}
```

One active run, two arms × four cases = **eight agent sessions**. Default to three minutes and eight visible actions per session including checking. Timebox the independent oracle to one minute per run. Total planned agent plus oracle time ≤32 minutes once cases are prepared. Two people have about four person-hours including collection and review; reserve time for one smoke test and environment trouble. Start with stdlib, Git and targeted tests. Aim for <1 GiB peak for the case driver and checks, excluding a separately measured local model; avoid whole-repository indexes. Cap each ledger at 64 KiB and each excerpt at 512 UTF-8 bytes. Reserve terminal summary space and count truncated events. Retain tiny fixtures or pinned reconstruction instructions; aim for <5 MiB of submitted artifacts. Record peak memory, wall time and artifact bytes, or state which measurement is unavailable.

## Required interface and acceptance

Implement commands equivalent to the following; these are proposed entry points. Run from the folder containing `cases.py`.

```bash
python cases.py validate --manifest cases.json
python cases.py smoke --backend fake
python cases.py run --case C02 --arm both --backend-config backend.json --out runs
python cases.py replay --case C02 --runs runs --offline
python cases.py report --runs runs --out reports
```

Offline replay rebuilds a report from saved observations without an API call. Keep optional live oracle re-execution a separate flag and state its dependency requirements. Output `cases.json`, four source/evidence bundles, eight arm summaries/ledgers, four case reports, one index and a short README with exact commands. Use stable case IDs and unique attempt IDs. Do not overwrite prior attempts. Acceptance requires matching input hashes within each pair, source support at s, reviewer sign-off or documented disagreement, real backend identity for each reported agent observation, a trace link for every behavioral conclusion, and a successful offline report rebuild. If a session is missing, list it explicitly; a scripted replay cannot fill it. In the index distinguish what the released skill detected from what the experimental verifier or humans established.

**Reference implementation patterns.** Harbor’s trajectory format associates tool calls and results with recorded steps; borrow the linkage without storing a full conversation. Mini-SWE-agent keeps agent, model and environment separate; one thin adapter and one local oracle suffice here. [Harbor trajectory specification](https://github.com/harbor-framework/harbor/blob/main/rfcs/0001-trajectory-format.md) · [Mini-SWE-agent implementation](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/agents/default.py)
