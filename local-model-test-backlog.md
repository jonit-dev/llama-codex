# Local Model Test Backlog

This backlog tracks local Ollama models tested for `llama-codex` agentic coding. The first acceptance target is simple: create or repair a tiny Python library/API implementation, run the provided tests, and verify they pass. The next target is a tiered benchmark suite with easy, medium, and hard fixtures.

## Standard Benchmark

Fixture:
- Work from a fresh copy of `models-testing-sandbox/base`.
- Implement `api.py` using only the Python standard library.
- Preserve the expected `create_app()` library entry point.
- Run exactly: `python3 -m unittest discover -s tests -v`.
- Pass all tests before final response.

Pass criteria:
- Direct instruction following works for a trivial prompt.
- Model makes real tool calls through `llama-codex`.
- Model edits the implementation instead of only planning.
- Model runs the tests and responds to failures.
- Final state passes the benchmark test suite.

## Tiered Benchmarks

| Tier | Fixture | Purpose | Status |
| --- | --- | --- | --- |
| Easy | `models-testing-sandbox/benchmarks/easy-api` | Single-file stdlib HTTP API with validation and route handling | Ready |
| Medium | `models-testing-sandbox/benchmarks/medium-task-library` | Multi-file package with domain model, service layer, filters, and JSON persistence | Ready |
| Hard | `models-testing-sandbox/benchmarks/hard-note-service` | SQLite-backed note service with import/export, search, and HTTP routes | Ready |

## Tested Models

| Model | Context | Direct Following | Tool Calls | Edit/Test Result | Decision |
| --- | ---: | --- | --- | --- | --- |
| `hf.co/unsloth/GLM-4.7-Flash-GGUF:UD-Q4_K_XL` | 32k/64k | Failed basic exact-response sanity | Not reliable | 64k failed with malformed/empty final; 32k was weak | Deleted; do not retry without a different template/runtime reason |
| `hf.co/yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M` | 32k | Failed exact-response sanity with channel markup | Failed | Printed pseudo tool calls as text; no edits; no tests | Deleted; do not retry |
| `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M` | 32k | Failed exact-response sanity with channel markup | Failed | Produced a plan and empty final; no edits; tests still failed at original `NotImplementedError` | Deleted; do not retry |
| `hf.co/bartowski/Qwen2.5-Coder-14B-Instruct-GGUF:Q4_K_M` | 32k | Passed exact `ok` sanity | Passed after XML tool-call parser patch | Easy run previously wrote invalid code. Medium retry read files via real tool call, then returned implementation in chat instead of editing files or running tests; independent tests stayed at 0/4. | Failed agent benchmark; lower priority than RNJ |
| `hf.co/deepreinforce-ai/Ornith-1.0-9B-GGUF:Q4_K_M` | 32k loaded / 64k advertised | Passed exact `ok` sanity | Passed after reducing visible tools to `exec_command` | Easy tier passed. Medium tier failed: partial broken multi-file edits, repeated repository rewrites, left `TaskService` unimplemented, and never reached a useful test-repair loop. A direct non-Codex medium prompt mostly echoed the test file and stopped after 484 chars. | Deleted; easy-tier only, not reliable for medium agentic coding |

## Observed But Not Yet Standardized

| Model | Note | Decision |
| --- | --- | --- |
| `qwen3-coder-30b-65k` alias for `hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:UD-Q4_K_XL` | Direct `/api/generate` sanity passed. Medium benchmark passed after proxy parser fixes for mixed prose/JSON and XML-style tool calls. Hard note-service benchmark passed through `llama-codex` at real Ollama `CONTEXT 65536`: read requirements/tests/source files, implemented SQLite store plus HTTP server, ran tests, repaired tag ordering, and independently verified 3/3 hard tests passing. | Current best candidate and default model |
| `qwen3-coder-next-tq1-65k` alias for `hf.co/unsloth/Qwen3-Coder-Next-GGUF:UD-TQ1_0` | Direct exact `ok` sanity passed and hard benchmark loaded at real Ollama `CONTEXT 65536`. The model used real `exec_command` tool calls, read tests and stubs, wrote SQLite store and HTTP server implementations, and ran tests. It then failed the hard repair loop: left `create_app` as an indented class/static method instead of the module-level function imported by `notes.__init__`, repeated server rewrites, made one malformed pseudo-parameter shell command, and independent verification failed at import time. | Hard-tier test-repair failure at `UD-TQ1_0`; do not judge higher quants from this result, but do not use this low quant as a replacement baseline |
| `north-mini-code-65k` alias for `hf.co/unsloth/North-Mini-Code-1.0-GGUF:UD-Q4_K_M` | Pull and 65k alias creation succeeded. Direct `/api/generate` sanity failed: for the exact prompt `Reply exactly with the single token: ok`, it returned a fabricated HTTP response and HTML page. Actual loaded sanity context was `CONTEXT 32768`; it was unloaded after the failed gate. | Direct-following failure; do not run agentic hard benchmark unless intentionally bypassing the sanity gate |
| `ornith-35b-65k` alias for `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M` | Pull and 65k alias creation succeeded. Direct `/api/generate` sanity failed: for the exact prompt `Reply exactly with the single token: ok`, it emitted a visible `<think>` block and then `ok`. Actual loaded sanity context was `CONTEXT 32768`; it was unloaded after the failed gate. | Direct-following failure; do not run agentic hard benchmark unless intentionally bypassing the sanity gate |
| `qwopus36-27b-coder-mtp-65k` alias for `hf.co/Jackrong/Qwopus3.6-27B-Coder-MTP-GGUF:Q4_K_M` | Pull and 65k alias creation succeeded. Ollama modelfile uses a bare `{{ .Prompt }}` template. Direct `/api/generate` sanity failed: for the exact prompt `Reply exactly with the single token: ok`, it emitted a visible `<think>` block and then `ok`. Actual loaded sanity context was `CONTEXT 32768`; it was unloaded after the failed gate. | Direct-following failure; do not run agentic hard benchmark unless intentionally bypassing the sanity gate |
| `qwopus36-27b-coder-compat-mtp-65k` alias for `hf.co/Jackrong/Qwopus3.6-27B-Coder-Compat-MTP-GGUF:Q4_K_M` | Pull and 65k alias creation succeeded. Ollama modelfile uses the same bare `{{ .Prompt }}` template shape as the main MTP variant. Direct `/api/generate` sanity failed with the same visible `<think>` block followed by `ok`. Actual loaded sanity context was `CONTEXT 32768`; it was unloaded after the failed gate. | Direct-following failure; compatibility variant does not fix the template/visible-thinking behavior |
| `hf.co/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF:Q4_K_M` | Direct `/api/generate` sanity passed, but `llama-codex` proxy run failed before generation with Ollama template HTTP 500: conversation roles must alternate. | Blocked by proxy/template compatibility; revisit only if stronger candidates fail |
| `hf.co/Mungert/SWE-agent-LM-32B-GGUF:Q4_K_M` | Direct sanity passed and parser patch fixed its mixed prose/JSON tool call, but it loaded at 28 GB with CPU spill and was too slow for practical use. | Deleted; too slow on this machine |
| `hf.co/unsloth/rnj-1-instruct-GGUF:Q4_K_M` | Direct `/api/generate` sanity passed. Medium benchmark made real progress: read tests, ran failing baseline, wrote an implementation, and reached 3/4 passing tests. It then looped on the remaining invalid-status failure without diagnosing that `list_tasks(status="blocked")` needed `ValueError`. | Near miss on medium; better than Ornith, but not a pass |
| `hf.co/Jackrong/Qwopus3.6-27B-Coder-GGUF:Q4_K_M` | Pulled after a long download but was not tested because Qwen3-Coder passed medium first. | Deleted during cleanup |

## Current Default / Baseline

`qwen3-coder-30b-65k` is the current default and baseline. It aliases `hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:UD-Q4_K_XL`, has passed the medium benchmark, and has one historical hard note-service pass with real tool use, file edits, test execution, repair, and independent verification at actual Ollama `CONTEXT 65536`.

Reproduction note from 2026-06-27: after adding stricter local edit shims, output caps, and shell-write rejection, fresh hard note-service reruns did not consistently reproduce the historical pass. `model_reasoning_effort=low` improved tool cadence, but Qwen still emitted placeholder file creation, malformed patch headers, shell-write attempts, and a top-level module that shadowed an existing package. The patched proxy now catches or repairs those cases, but the hard rerun still cycled without implementing the package files. Treat the historical pass as evidence that this model can do the task, not as evidence that `llama-codex` is currently more reliable than `aider diff-fenced`.

Update from the same date: the `llama-codex` harness now has a verification
retry loop with workspace-change detection and a proxy guard for premature
prose-only responses. In the UI trip-planner repair benchmark, Qwen first
stopped after saying it would fix the implementation; the proxy converted that
into a failing `exec_command` diagnostic, Codex stayed in-session, Qwen emitted
a valid patch, and `npm test` passed. This materially improves reliability for
the "stops out of nowhere" failure mode, but more varied project runs are still
needed before promoting `llama-codex` over `aider diff-fenced`.

Harder greenfield follow-up: the bookmark-vault benchmark added JSON
persistence, search/filtering, import/export, and a CLI. Qwen failed through
`llama-codex` even after the premature-stop recovery. It repeatedly read files
and stopped in prose, attempted invalid hunks against hallucinated code, tried
to remove `bookmarks/vault.py`, then continued to issue diagnostic commands
after forced-patch retry prompts. The harness now rejects `rm`/`unlink` source
edits and can enforce patch-first recovery by rejecting `find`/`ls`/`cat` style
commands during those retries. This is safer, but the model still did not
produce a valid implementation. Treat this as evidence that prompt/harness
guards are improving safety, not enough to make `llama-codex` the default
greenfield SWE harness over `aider diff-fenced`.

Later bookmark-vault iterations improved that result but did not flip the
verdict. After adding retry workspace snapshots, raw patch-block translation,
full-file replacement enforcement during no-change recovery,
`git apply --recount` fallback, missing `+` repair in `Add File` patches,
heredoc-close repair, and increasing `LLAMA_CODEX_MAX_OUTPUT_TOKENS` to 4096,
Qwen generated a substantial `bookmarks/vault.py` implementation. The CLI test
passed, but two library tests still failed: nested tag lists were shallow-copied
and validation messages used uppercase `URL`/`Title` instead of matching
`url`/`title`. Qwen diagnosed both bugs but kept failing the edit channel with
unsupported native `apply_patch`, bad hunks, `sed -i`, `rm`, and prose stops.
Current conclusion: these patches materially improve recovery, but
`llama-codex` remains below `aider diff-fenced` as the default greenfield
harness for this Qwen model.

Follow-up harness pass: `llama-codex` now isolates local Codex config by
default with `mcp_servers={}`, `plugins={}`, and `marketplaces={}`, which
prevented inherited Playwright MCP startup during the bookmark-vault CLI
benchmark. Verified runs now also have `LLAMA_CODEX_ATTEMPT_TIMEOUT_SECONDS`
so a prose-only or no-edit Codex attempt is terminated and retried instead of
hanging. The proxy gained fail-closed native `apply_patch` diagnostics, repair
for wrapped unified diffs, malformed `--/++` diff headers, complete heredocs
with missing `+` prefixes after `*** Add File`, and heredocs missing the final
`*** End Patch`. Regression tests cover these cases. This is meaningful harness
stability progress, but the benchmark has still not produced an independently
passing bookmark-vault run through `llama-codex`.

Additional patch-channel hardening: the proxy now tries `git apply -p0` before
falling back to `patch`, and normalizes unified diff headers that contain
absolute paths under the current workspace back to relative paths. These fixes
target two fresh Qwen failure modes observed in bookmark-vault: `--- bookmarks/...`
diffs were treated as `vault.py` by default `git apply`, and absolute
`--- /home/.../bookmarks/vault.py` headers were rejected as unsafe. The latest
run again reached a real implementation plus focused two-failure repair loop
before exposing these path-normalization issues. Harness stability improved;
bookmark-vault still needs a clean pass before changing the recommendation.

Latest bookmark-vault harness pass: the proxy removed the non-atomic system
`patch` fallback after it partially applied a bad unified diff with fuzz and
left a `.rej`. Forced no-change recovery now releases once the conversation
contains successful patch output, so verification commands are not falsely
rejected after a patch. Dirty repair prompting was tightened, and the proxy now
rejects subsequent full-file rewrites after a prior successful patch, requiring
targeted `*** Update File` repairs instead. Regression tests cover these paths.
The benchmark still has not passed: Qwen can reach a near-working package but
continues to miss or loop on small semantic fixes such as deep-copying nested
tag lists and matching exact error text.

New candidates should run the hard note-service benchmark for acceptance. Medium remains useful for wrapper debugging or quick smoke tests, but it is not enough to qualify a model for repo work.

## Cleanup Findings

After the failed candidate pass, local Ollama storage was cleaned so only `qwen3-coder-30b-65k` remains from this benchmark set. Removed entries included Qwen3-Coder-Next `UD-TQ1_0`, Qwen3.5 SWE-agent 9B, North Mini Code, Ornith 35B, both Qwopus3.6 variants, the duplicate `qwen3-coder-30b-32k` alias, and the experimental `qwen3-coder-30b-128k` / 1M model entries. The failed hard run copy at `models-testing-sandbox/runs/qwen3-coder-next-tq1-hard` and temporary alias files under `models-testing-sandbox/models/` were also removed.

Retain only `qwen3-coder-30b-65k` unless a new candidate passes direct sanity and the hard benchmark. The 65k alias points at the accepted baseline blob with actual `num_ctx 65536`; the removed 32k alias was redundant, and the removed 128k/1M entries were separate experiments that were not the accepted baseline.

## Current Queue

| Priority | Model | Purpose | Status |
| ---: | --- | --- | --- |
| 1 | `hf.co/unsloth/Qwen3-Coder-Next-GGUF:UD-Q4_K_M` | Qwen coding-agent successor with 256k advertised context and explicit tool-use focus | Deferred; `UD-TQ1_0` failed hard repair and was removed, so only a higher-quant hard pass can justify replacing the baseline |
| 2 | `hf.co/unsloth/North-Mini-Code-1.0-GGUF:UD-Q4_K_M` | 30B-A3B code model trained for agentic software engineering, terminal tasks, and tool use | Failed direct exact-response sanity via `north-mini-code-65k`; removed after cleanup |
| 3 | `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M` | Larger Ornith agentic-coding release with reported tool-call and SWE-bench strength | Failed direct exact-response sanity via `ornith-35b-65k`; removed after cleanup |
| 4 | `hf.co/Jackrong/Qwopus3.6-27B-Coder-MTP-GGUF:Q4_K_M` | 27B dense agentic coder with tool-use/function-calling training | Failed direct exact-response sanity via `qwopus36-27b-coder-mtp-65k`; removed after cleanup |
| 5 | `hf.co/Jackrong/Qwopus3.6-27B-Coder-Compat-MTP-GGUF:Q4_K_M` | Compatibility variant of Qwopus3.6 27B coder for template/tool-call fallback | Failed direct exact-response sanity via `qwopus36-27b-coder-compat-mtp-65k`; removed after cleanup |

## Testing Notes

- Do not judge a model from chat quality alone. Record direct sanity, tool-call behavior, edit behavior, test behavior, and final test result.
- A model that only prints plans or pseudo tool calls fails the agent benchmark.
- A model that reads a PRD, restates the task, and stops before inspecting or editing files fails PRD execution. Default steering now explicitly tells the model not to stop after restating a PRD and to begin the first concrete implementation or test slice.
- Default steering includes compact-action rules inspired by the caveman skill's useful behavioral constraints: avoid filler, avoid obvious tool-use narration, avoid task restatement, quote concise errors, and report only changes, verification, and risks at completion.
- A model that can call tools but cannot pass the hard benchmark through inspect/edit/test/repair is not good enough for the first goal.
- Keep one model loaded at a time. Use the `qwen3-coder-30b-65k` alias as the current baseline; use 32k only when testing smaller or unknown candidates to reduce memory pressure.
- The default lean tool profile hides bulky non-coding tools and `write_stdin`; repeated Qwen3-Coder harder runs called `write_stdin` with bogus session IDs, causing `Unknown process id` tool-routing errors. Use `--llama-tools standard` only when interactive/long-running command sessions are required, `--llama-tools full` only when testing whether a hidden integration tool is required, and `--llama-tools tiny` only for strict command-execution benchmarks.
- The wrapper advertises the configured context window to the CLI, but the proxy does not yet force Ollama `num_ctx`; confirm actual loaded context with `ollama ps`.
- Proxy parser fixes changed the results materially: mixed prose followed by bare JSON tool calls and XML-style `<tool name="..." function="..."/>` calls now translate into real function calls. Retest previously failed models only when the failure mode was tool-call formatting, not weak implementation.
- Ornith improved materially after hiding MCP/resource/plugin tools. A temporary stricter profile exposed only `exec_command`; Qwen3-Coder later showed the same narrower surface is also useful for avoiding invalid `write_stdin` calls.
- Ornith medium failure looks primarily model-side after the tool-surface patch: proxy logs showed only `exec_command` was exposed and backend requests completed, while the model generated incomplete/broken code. Direct Ollama prompting on the same medium fixture also failed to produce a usable implementation.
- `LLAMA_CODEX_CONTEXT_WINDOW=65536` improves the CLI-side budget, but Ollama `/v1/responses` ignores request-level context overrides. Use a model alias with `PARAMETER num_ctx 65536` when the backend must actually load a 65k context.
- Avoid retesting deleted Fable/Composer variants unless the wrapper changes to a different native Ollama tool protocol.
