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
