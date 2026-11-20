# DocAgent evaluation pipeline

Two independent packages and a thin layer that joins them. Requirements live in
`docs/requirements/`. Everything here is standard-library Python (3.10+) and Git.

| Path | What it is | Runs without |
|---|---|---|
| `case_studies/` | Task 1. Collect staleness cases, run blind and checked reuse, rebuild an offline report. | SWE-bench, the benchmark package |
| `paired_runs/` | Task 2. Prepare an issue, build memory at an older commit, run three arms, grade, report. | the case-study package |
| `backends/` | Agent adapters behind one file contract: a deterministic fake and a tool loop for a chat endpoint. | each other |
| `integration/` | Converts one benchmark trace into a case bundle. Reads and writes files only. | importing either package |
| `validate_pipeline.py` | One explicit SWE-bench Lite instance, end to end. | a batch: it refuses lists and wildcards |
| `grader/` | Runs the official SWE-bench harness on a Linux host with Docker. | this repository's other code |

Neither package imports the other. They meet only through the files described below.

## Quick checks (no key, no network, no Docker)

```bash
python experiments/paired_runs/bench.py smoke --backend fake
python experiments/case_studies/cases.py smoke --backend fake
python -m unittest tests.test_experiments
```

A fake or replayed session is marked `is_live: false` everywhere and is never counted as an agent observation.

## One-issue validation

```bash
python -m experiments.validate_pipeline --instance-id <real-lite-id> \
    --backend-config experiments/backends/backend.example.json \
    --study experiments/paired_runs/study.example.json \
    --out experiments/out/pilot --push-grading
```

It prints a preview (one id, two evaluator controls, three live attempts, the limits) and then runs
`preflight -> prepare -> controls -> solve -> grade -> report`. Each stage can be rerun alone with
`--stage NAME`; finished attempts are never repeated and never overwritten. The solve stage will not
start until the unmodified base fails a FAIL_TO_PASS test and the reference patch resolves under the
official harness. Output: `OUT/validation/summary.json` with three separate verdicts (environment
controls, pipeline acceptance, agent resolution per arm).

Batches are a different command and are opt-in: `bench.py run --manifest ... --batch`.

## What is released DocAgent and what is experimental

- **Released, unchanged:** routing (`context_bundle`) and the file-level freshness signal in
  `skills/docagent/scripts/docagent.py`. A changed file is a reason to inspect a claim, nothing more.
- **Experimental:** the claim-level checkers (`paired_runs/prlib/checker.py` and the verifier inside
  `case_studies/cases.py`). They are named `experimental-...` in every manifest, trace and report.

## Backend contract

An adapter is any command that accepts `--request request.json` and `--capabilities`.

| Request | Result |
|---|---|
| `schema_version`, `run_id`, `workspace`, `issue_text`, `role`, `prompt_path`, `context_paths`, `handoff_path`, `limits {time_s, max_actions}`, `read_only`, `seed`, `out {events, result}`, `backend` (settings) | `status`, `exit_reason`, `is_live`, `backend {agent, model, version, quantization, location}`, `capabilities`, `elapsed_ms`, `actions`, `usage {input_tokens, output_tokens, cache_read_tokens, source}`, `final_answer` |

Events are JSON lines: `tool_call` (tool, path, range, short args and result), `refused`, `message`,
`terminal`. The caller, not the adapter, captures the diff from the workspace. Unknown values are
`null`; token counts are provider-reported or absent, never estimated.

`backends/toolloop_agent.py` gives the model five tools (`list_dir`, `read_file`, `search`,
`replace_in_file`, `finish`) confined to the workspace. There is no shell and no network tool, so the
model cannot read the grader store, the Git history or another attempt. It speaks the native Ollama
chat API or any `/chat/completions` endpoint; credentials come from the environment variable named in
`api_key_env`. Copy `backends/backend.example.json` and edit it; never put a key in the file.

## Official grading without local Docker

`paired_runs/bench.py grade` writes a request (official predictions JSONL plus the two controls) and
never grades anything itself. The request is run by `grader/remote_grade.py`:

- on a Linux host with Docker: `python experiments/grader/remote_grade.py --request R/request.json --out RESULTS`
- or on GitHub Actions: `bench.py grade ... --push` publishes the request on a `grading/<id>` branch;
  `.github/workflows/swebench-grade.yml` runs the pinned harness and commits its reports to that branch;
  the same command then fetches them into the grader store.

The grader loads the dataset from the parquet file of the pinned revision, uses one worker, and keeps
the harness's own `report.json` and per-test output. Because the harness skips empty predictions, the
base control uses the harness's negative-test mode (`skip_patch=True`).

## Where things are kept

- `experiments/.cache/` (ignored): pinned dataset rows without the fix, bare clones, snapshot tars.
- `experiments/.grader_store/` (ignored): test-name lists, relevance annotations, official reports.
- Solver workspaces: a temporary directory outside the repository, deleted after each attempt.
- The reference patch, the evaluator test patch and the eval script are never stored locally.
