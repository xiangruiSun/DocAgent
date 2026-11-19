# Claude Code handoff · Build DocAgent and validate one real issue

Implement this in the DocAgent repository. Inspect the checkout and its existing tests first, report its SHA and preserve user changes. Use cfd5224 as the documented reference. The two full team requirements follow this directive. They define the pipeline the teams will later use. **For this assignment build the pipeline and prove one vertical slice works. Stop after that validation.** The execution limits here take precedence over the appendices' collection and study quotas.

## Deliverables

1. Implement both independent entry points from the appendices, or document equivalent commands. Keep each runnable without importing the other team’s package or requiring its results. Add a thin optional integration command that orchestrates their public inputs/outputs. Use existing DocAgent routing and governance code where applicable. Keep any experimental claim checker clearly identified. Provide configurable real-agent and evaluator adapters, a no-key smoke test, and an offline report command. Use one real backend available to the operator. Keep tokens, costs and unsupported telemetry nullable. Publish a redacted example configuration.
2. Provide a one-issue validation command such as `python -m experiments.validate_pipeline --instance-id <real-lite-id> --backend-config <config> --out <dir>`. Require exactly one explicit instance ID. Resolve it from a pinned revision of the actual SWE-bench Lite test split. Reject wildcards, empty selection, and multi-ID manifests at this entry point. Preview the one ID, two evaluator controls, three live solver attempts and limits before execution. Provide a separate explicit batch entry point for later team use; keep batch execution opt-in.
3. Keep preflight, prepare, solve, grade and report independently restartable. Record repository, dataset, evaluator and environment revisions, hashes, commands, model, timings and terminal states. Cache images and case inputs. Preserve each prior attempt and only resume unfinished stages. Capture enough evidence that a teammate can distinguish a grader problem from a failed generated solution.

## Required live acceptance run

- Check available backend credentials or local endpoint, isolated solver workspace, Docker or remote official evaluator, CPU, RAM and free disk. Use one worker and reuse a prepared image. Budget about 30 minutes of warm solving/grading across three arms, with an initial six-minute policy-plus-solver deadline per arm. Record cold setup separately and use a configurable outer timeout (suggested 60 minutes including provisioning). If this host cannot grade, accept the official report from a separately configured grader running the identical case. Stop with a precise blocker when no working grader/backend exists. Do not represent a dry run as acceptance.
- Select one **development pilot** with a reproducible environment and an old claim supported at ancestor s whose evidence changes by the benchmark’s pre-fix SHA t. Determine relevance from the issue and permitted source. Freeze the ID and old/current evidence before the live attempts. Reserve this pilot from future held-out evaluation. If a controlled claim is used for a diagnostic, record its provenance and keep its result separate from real drift. Ensure at least one check/repair/omit path is exercised by deterministic tests even if the router misses the claim in the live run.
- Use the official SWE-bench evaluator to establish the environment controls: run the original unmodified base against the designated evaluator tests and confirm an expected FAIL_TO_PASS failure, then verify the official reference patch resolves the instance. Some harness versions skip empty predictions before running tests. A skipped empty prediction does not establish the negative control. For that case run the same evaluator test script on the unmodified base and retain actual per-test output. Keep the reference patch, evaluator test patch and all grades inaccessible to the builder and solver.
- Run the same real issue under **source only**, **static stale**, and **selective stale**, one real solver attempt per arm. Use identical backend/model, role prompts, agent tools, budgets and clean base snapshots. Static and selective must share the initial stale packet hash. Record final packet hashes, checker decisions, structured tool events, planner handoff and actual unified diff. Ordinary source exploration is allowed. Preserve empty or invalid submissions as observed failures. No human editing of generated patches.
- Use the official grader on each gradeable generated patch in a clean environment and retain its report. No proposed patches, invented grades, replayed model sessions or mocked Docker responses count toward this step. Replay **one** live trace as a Task 1 case report using a small format adapter in the integration layer; copy a minimal self-contained evidence bundle into the case tool’s input format. Verify in a clean process that the report regenerates without model calls or the other package. Reusing this pilot tests integration only.
- Verify deadlines, reset isolation, no generated memory in the source-only workspace, initial packet equality, expected hidden-file boundaries, unique run IDs, clean patch application or recorded failure, trace truncation with terminal counters retained, and resume without duplicate paid calls. Use small local regression tests for edge cases. Print commands and exit statuses actually observed.

## Completion decision and stop rule

Report three separate statuses: **environment controls**, **pipeline acceptance**, and **agent resolution per arm**. Claim pipeline acceptance only if both controls behave as expected, all three live attempts have recorded terminal states, at least one unedited model-generated patch successfully applies and reaches a conclusive official grade, and the compact case report replays offline. A valid generated patch may fail the issue tests while still demonstrating that generation, application and grading work. Three empty predictions, a gold-only pass or an infrastructure error leaves the relevant gate incomplete. Diagnose recoverable implementation problems and rerun only affected stages within budget; give any necessary new solver call a fresh attempt ID and disclose it. Never retry simply to obtain a passing patch.

Return a short run summary with instance ID, s/t SHAs, model/backend, actual host or grader, commands, three arm results, control results, elapsed time, memory where available, and links to manifest, submitted diffs, official reports and replayed case. Mark performance conclusions as pending the held-out study. **Stop after this one development issue. Do not collect four cases, launch the 6/12/18/28-run cohorts, or start a background batch.**

---


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


# Task 2 · Run the paired DocAgent issue-resolution experiment

## Assignment for Claude Code

Implement a small reproducible benchmark under `experiments/paired_runs/`. Your two-person team owns its issues, memory construction, checker, backend, isolated workspaces, grading and analysis. A clean checkout of DocAgent and public benchmark data must suffice. Do not wait for another pair’s cases, traces, labels or code. The primary question is whether selective checks on stale, task-relevant memory improve test-based patch resolution within a fixed budget. Secondary questions concern duplicated exploration, harmful use of outdated claims and the cost of maintenance.

**Starting point.** Work from [DocAgent v0.14.2 at cfd5224](https://github.com/xiangruiSun/DocAgent/tree/cfd5224729c8b2eb7502e51934aa2a2a38501357). Record the actual source SHA and your driver revision. Inspect `skills/docagent/scripts/docagent.py`, especially `context_bundle`, and `scripts/demo.py`. The released router produces ranked metadata and file-level freshness findings. Read the selected bodies to assemble the packet. A changed file is a reason to inspect a claim. A receipt or a Git anchor records review history; it cannot establish what an API currently does.

**Backend contract.** The developer can use Claude Code or any coding assistant to implement this brief. The *experimental agent* is separately configurable. Support one real backend chosen by the pair, plus a deterministic fake for smoke tests. Expose a neutral adapter callable or an external command that consumes a request JSON path and emits event JSONL, a result JSON and any patch. A CLI such as Claude Code, an agent using a GPT API, or a local coding model driven by a small tool loop can all satisfy this boundary. A text-completion endpoint needs a tool loop or equivalent file-edit interface. Avoid implementing multiple vendor SDKs just to demonstrate portability. Launch commands as argument arrays. Receive provider credentials through the environment and store only a redacted configuration. A fake or replay can test the recorder and the adapter but contributes zero agent observations.

| Request fields | Response and capability fields |
|---|---|
| schema_version, run_id, workspace, issue_text, role, prompt/context paths, time and action limits, optional model ID/seed | status, actual backend/agent/model/version, observed tool events, elapsed_ms, usage when exposed, diff path or explicit no_patch, exit_reason |
| capabilities declared at preflight | can_reset_session, can_limit_time, can_count_actions, can_capture_diff, observable_reads, usage_source; unknown values are null |

Allow any CPU/GPU, OS or remote inference endpoint. Record host, CPU, system RAM, GPU/VRAM when present, OS, backend location and model quantization if known. A hosted API moves inference off the local PC; report local peak memory and leave remote memory unknown. Count provider-reported input/output/cache separately and document cache semantics. Never substitute a heuristic token estimate for measured usage. For a backend with hidden operations, mark affected metrics unavailable. Capture observable file/tool events and short responses, excluding private reasoning, credentials and bulk transcripts.

## Staff and scope

| Owner | Independent work | Interface between teammates |
|---|---|---|
| A · issue preparation and evaluator | Pin the dataset, select candidates, prepare restricted snapshots, run empty/reference controls, supply claim packets and grade submitted predictions | Produce manifest + issue text + clean workspace + hashed packet. Accept an instance ID and unified diff. Supply a toy fixture first. |
| B · execution and analysis | Implement backend adapter, budget accounting, policy selection, planner/implementer sessions, trace reduction, paired tables and restart | Develop against a tiny independent fixture and fake adapter; consume A’s frozen manifest for live runs. |

Use one fixed solver configuration for the main experiment. You may use Claude Code, a GPT-powered coding agent, mini-SWE-agent or SWE-agent with a hosted or local model. A backend is eligible for the primary cohort if it can start clean, accept exactly the supplied context, isolate filesystem access, enforce the declared wall/action limits and return an actual diff. The same pair of people may work on different machines. Assign **all arms of one issue to the same machine and provider setup**. Prefer one setup across the cohort; if unavoidable, freeze setup blocks by issue, disclose them and show separate results. Switching model midway through an issue requires rerunning every arm of that issue under the new setup as a separate block. Do not compare a Claude run with memory against a GPT run without memory.

## Run count and feasibility decision

| Priority | Design | Held-out solves |
|---|---|---:|
| Minimum | Two distinct issues, preferably from two repos, each under source only, static stale and selective stale | 6 |
| Default | Four distinct issues × the same three arms | 12 |
| Expansion | Six issues × three arms | 18 |
| Optional proposal comparison | Add five arms to each of two prespecified issues in the six-issue cohort: static fresh, selective fresh, released DocAgent fresh/stale, full current-source rebuild | +10, 28 total |

Two people × about two hours each gives four person-hours for Task 2. With one shared PC and both people working together there may be only two elapsed machine-hours. Calibrate on one disjoint pilot issue with all three arms. Record cold setup, validation, packet construction, time to grade from a clean snapshot, solver time and failures. Select the largest **complete** core tier that fits before viewing held-out outcomes. Budget conservatively using the slowest pilot cell, include per-issue preparation and reserve at least 20 minutes for retries/reporting. Example: 120 minutes available minus 45 minutes already spent on setup/pilot minus 20 minutes reserve leaves 55 minutes. At eight minutes per warm cell and negligible additional provisioning this fits six cells. At five minutes per cell it still does not fit twelve. More people or a hosted API alone does not increase grader throughput. The 28-run proposal extension needs measured spare capacity. When only the core fits, RQ3 estimates selective vs blind reuse; full rebuild and released-workflow comparisons remain unmeasured. Time targets assume a working adapter and evaluator; record engineering hours separately if setup consumes the session.

## Data preparation and leakage controls

1. Pin SWE-bench Lite dataset revision, split and evaluator revision. Start from pytest, Sphinx and SymPy Lite instances. Publish the seed (suggested 20261119), sorted then shuffled candidate IDs per repository, selection order and reasons for exclusions. Round-robin across available repositories. Reserve the pilot first. Avoid selecting an issue because a particular model previously solved it.
2. For each candidate resolve pre-fix SHA t and nearest first-parent ancestor s at least 30 days earlier. An issue is eligible if the environment is reproducible and its history contains a task-relevant claim that naturally changed. Annotate relevance against the issue and pre-fix source, without reading the fix. Include router misses and preserve the screening log. If the cohort cannot fill within the timebox, reduce to a smaller complete tier. Label any controlled-fixture runs separately; they are never SWE-bench resolutions.
3. Build memory at s and optionally at t using a deterministic issue-blind builder. Emit bounded Markdown documents and a claim index containing claim ID, text, covered path, qualified symbol, predicate type/arguments and evidence revision. Start with Python signatures and literal module/config defaults; add location and existing-test predicates only if supported within the pilot budget. Group by module using fixed rules and a frozen size limit. Hash the inventory. Record skipped predicate types and truncated coverage. Original upstream repository notes remain visible in every arm. Keep generated memory files, DocAgent hooks and generated instructions out of the source-only checkout.
4. For the builder and solver export only allowed history or clean snapshot trees; exclude future Git objects/refs, gold diff, benchmark test patch, supplied solution, labels, grading output and other attempts. Give the grader separate storage. The solver may run tests already present at t. Permit the model API via the adapter, with external browsing, local conversation recall and automatic cross-run memory disabled. Verify on the pilot that an empty patch fails the designated issue tests and the reference patch passes the official grade. Use evaluator-only reference patch validation for held-out environment screening too. Budget this work once per issue.
5. Freeze a manifest listing pilot/held-out status, repo, instance ID, s/t, environment digest, builder/checker/adapter versions, backend/model settings, limits, arm order and initial packet hash. For each issue, cache the **one** stale packet returned by the released router, including the observable freshness metadata; read the bodies and enforce the document/token cap. Replay those exact bytes into static and selective preprocessing. Log token accounting method and treatment of cached work.

## Experimental intervention

| Arm | Required behavior |
|---|---|
| Source only | Use issue text, upstream instructions and ordinary source tools. Inject no generated claim or metadata. |
| Static stale | Give the agent the routed packet built from s. Preserve order, metadata, prompt slot and truncation. It may question the note and inspect live source. |
| Selective stale | Start from identical packet bytes. For up to three suspect claims in retrieval order, check recorded evidence at t. Log supported, contradicted, unresolved, or skipped with reason. Reuse supported; repair only from unambiguous current evidence; omit other suspect assertions with a source pointer. Untouched claims remain explicitly unchecked. |
| Optional arms | Static/selective fresh apply the same policies to memory built independently at t. Released DocAgent runs its normal review and sync obligations at the assigned freshness; charge for those actions. Rebuild generates memory anew at t online, then solves. Record whether its final packet matches fresh static. |

Use the existing file-change signal as a trigger, including committed changes s→t; test this explicitly. For unsupported paths or dynamic behavior return unresolved. A renamed symbol needs more than a missing file to justify a new location. Restrict automatic repairs to deterministic evidence-backed templates during the pilot. The experimental checker must never use evaluator answers, task-relevance labels or the other pair’s annotations.

For RQ1, run a short read-only planner and a fresh implementer session with the same model in every arm. Planner gets at most two visible actions and writes a handoff of at most 160 measured tokens (or a fixed 600-byte cap, uniformly if tokenizer unavailable). Implementer gets the same arm context and the handoff. No previous conversation leaks across roles. Balance arm order within issues using the recorded seed. Keep tool set, context position and decoding configuration fixed. No human correction after an attempt starts.

## Resource controls and observations

Run one solver or grader worker per resource-constrained host; avoid concurrent model loading and grading. Prefer an already available API if local inference would exceed available RAM, or use a CPU/GPU local model if it passes the same pilot. Host and grading machine may differ. A reasonable starting cap per solve is **six minutes, 12 visible tool actions and five documents/2,000 memory tokens**. The checker's maximum 45 seconds/three checks, the planner and the implementer all draw from that one allowance. Enforce deadline on subprocess trees and API requests. Track cumulative model tokens, with a 16,000-token ceiling only if the adapter can reliably enforce it; otherwise use the same enforceable time/action limits for the *entire* comparison and disclose the token limitation. For opaque agent CLIs, count actual observed tool calls via native events/hooks; if caps cannot be enforced select another adapter or explicitly run a separately labeled time-only pilot. A conservative fixed UTF-8 byte ceiling can serve as a common context bound when tokenizer access is unavailable; record bytes as bytes. Freeze budget definitions during the pilot.

Target a 16 GiB host. For officially graded SWE-bench, plan for its published 8 CPU cores and 120 GB free storage; one worker and preselected images reduce concurrency but cannot guarantee that each individual environment fits. Keep two GiB host memory headroom where practical. Record host-wide peak used memory, available memory, peak process/container memory when exposed, and VRAM separately. If local grading is infeasible, use the same official evaluator on another machine or its supported cloud route for all arms. An ungraded patch may be retained as pending and graded later; no pending result counts as a success. Keep scratch Docker images outside report artifacts. [Official evaluator and cloud options](https://www.swebench.com/SWE-bench/guides/evaluation/) · [Hardware guidance](https://github.com/SWE-bench/SWE-bench#usage)

Write JSONL incrementally. Include run/attempt ID, event sequence, arm, role/stage, elapsed time, tool/action, normalized path/symbol/range, claim ID, short observation and counter deltas. Store the exact routed packets once by hash; retain planner note, submitted diff, evaluator report and status per attempt. Limit excerpts to 512 UTF-8 bytes and each event ledger to 64 KiB. Reserve terminal summary space; accumulate all counts independently of the log cap. Flag truncation and observational coverage. Hashes alone cannot explain an action; retain small source excerpts for repairs. Exclude credentials and unbounded native transcripts.

## Grading and scientific outputs

Save each prediction in official JSONL with instance_id, model_name_or_path and model_patch. Use a unique run_id per arm/seed/attempt so evaluator caching cannot return another arm’s result. Apply the patch to a clean t environment, then run the hidden evaluator tests. Require its full resolution outcome, covering designated FAIL_TO_PASS and PASS_TO_PASS behavior. Preserve patch-generation status, apply status and grading status separately. Measure evaluator time outside the solver allowance but inside total machine time. Online timeout, invalid patch and model budget exhaustion count as solver failures. Retry an infrastructure interruption once, using identical inputs and recording both attempts; persistent infrastructure issues are missing data. No second model attempt based on grader feedback.

```bash
python -m swebench.harness.run_evaluation --dataset_name SWE-bench/SWE-bench_Lite --split test --instance_ids INSTANCE_ID --predictions_path predictions.jsonl --max_workers 1 --run_id UNIQUE_ATTEMPT
```

| Output | Calculation and denominator |
|---|---|
| Primary paired success | Per issue, list three binary resolutions or missing. On complete static/selective pairs, difference = (selective-only wins − static-only wins) / number of pairs. Show both-pass, neither-pass, discordances, missing outcomes and sensitivity to missing outcomes. Issues are the independent units. |
| RQ1 · exploration and handoff | Per arm count searches/reads until first evaluator-annotated relevant source, fraction reaching it, distinct paths, and implementer reads overlapping planner reads on the same revision/path/range divided by all observed implementer reads. Show never reached, unavailable tracing and zero denominators separately. Path-only overlap can be a separately labeled proxy. |
| RQ2 · outdated claims | Count eligible contradicted claims, routed, exposed, acted upon, corrected and unresolved. Review observed commands/edits before attributing use. Missed routing and wrong edits despite good evidence are separate outcomes. |
| RQ3 · checking cost | Per issue show check count/time, rejected supported claims over supported routed claims, repair correctness, solver time, total time and model usage. Separate offline build, online route/check/sync, planning/implementation and grading. Charge cached routing equivalently for paired policy accounting; also report physical wall time. For rebuild scenarios show build/H + mean online cost for H=1,5,20; charge fresh rebuild once per query. |
| Interpretation | Report counts, paired differences and individual traces. At two to six issues a single success changes the estimate substantially. No population-wide speedup or significance claim. If hosts differ, compare timings within matched issues and identify execution environments. |

## Entrypoints, artifacts and definition of done

Implement equivalent commands; run them from the package directory. The manifest and adapter config hold concrete paths and revisions.

```bash
python bench.py smoke --backend fake
python bench.py prepare --config study.json --out prepared
python bench.py pilot --config study.json --backend backend.json
python bench.py run --manifest frozen.json --backend backend.json --resume
python bench.py grade --manifest frozen.json --workers 1
python bench.py report --manifest frozen.json --out report
```

Support resume by (manifest hash, instance, arm, solver config hash, seed, attempt). Atomically persist terminal states; refuse to combine incompatible configurations; keep interrupted attempts for audit. Accept when a fresh checkout can run a no-key smoke test, all three arms exercise their distinct code paths, source-only sees zero generated documents, identical static/selective initial hashes and a known harmless-drift control pass, hidden files cannot be read from solver workspaces, a real pilot produces a gradeable diff, and report regeneration needs no model calls. Submit the frozen manifest, candidate/exclusion list, backend config without keys, predictions, compact traces, official grades and per-issue CSV/Markdown. Report actual run counts, resource peaks, missing data and implementation limitations. Mark a blocked experiment as blocked with the last verified artifact; never substitute smoke outcomes for held-out results.

**Implementation precedents.** Mini-SWE-agent's default agent separates model interaction from environment execution. Harbor supports distinct agent integrations and a common representation for steps and tool results. Aider reports editing behavior alongside benchmark outcomes; log patch creation/application separately from test success. SWE-bench accepts per-instance predictions independently of which coding agent produced them. Use these seams without deploying additional frameworks or services. [Mini-SWE-agent source](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/agents/default.py) · [Harbor adapters](https://docs.harborframework.com/agents/pre-integrated-agents) · [Harbor traces](https://github.com/harbor-framework/harbor/blob/main/rfcs/0001-trajectory-format.md) · [Aider benchmarks](https://aider.chat/docs/leaderboards/) · [SWE-bench evaluation guide](https://www.swebench.com/SWE-bench/guides/evaluation/)
