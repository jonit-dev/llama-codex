# Local Model Test Backlog

This backlog tracks local Ollama models tested for `llama-codex` agentic coding. The first acceptance target is simple: create or repair a tiny Python library/API implementation, run the provided tests, and verify they pass. The next target is a tiered benchmark suite with easy, medium, and hard fixtures.

## Standard Benchmark

Fixture:
- Work from a fresh copy of `models-tesitng-sandbox/base`.
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
| Easy | `models-tesitng-sandbox/benchmarks/easy-api` | Single-file stdlib HTTP API with validation and route handling | Ready |
| Medium | `models-tesitng-sandbox/benchmarks/medium-task-library` | Multi-file package with domain model, service layer, filters, and JSON persistence | Ready |
| Hard | `models-tesitng-sandbox/benchmarks/hard-note-service` | SQLite-backed note service with import/export, search, and HTTP routes | Ready |

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
| `hf.co/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF:Q4_K_M` | Direct `/api/generate` sanity passed, but `llama-codex` proxy run failed before generation with Ollama template HTTP 500: conversation roles must alternate. | Blocked by proxy/template compatibility; revisit only if stronger candidates fail |
| `hf.co/Mungert/SWE-agent-LM-32B-GGUF:Q4_K_M` | Direct sanity passed and parser patch fixed its mixed prose/JSON tool call, but it loaded at 28 GB with CPU spill and was too slow for practical use. | Deleted; too slow on this machine |
| `hf.co/unsloth/rnj-1-instruct-GGUF:Q4_K_M` | Direct `/api/generate` sanity passed. Medium benchmark made real progress: read tests, ran failing baseline, wrote an implementation, and reached 3/4 passing tests. It then looped on the remaining invalid-status failure without diagnosing that `list_tasks(status="blocked")` needed `ValueError`. | Near miss on medium; better than Ornith, but not a pass |
| `hf.co/Jackrong/Qwopus3.6-27B-Coder-GGUF:Q4_K_M` | Pulled after a long download but was not tested because Qwen3-Coder passed medium first. | Deleted during cleanup |

## Current Queue

| Priority | Model | Purpose | Status |
| ---: | --- | --- | --- |
| 1 | `hf.co/Mungert/SWE-agent-LM-32B-GGUF:Q4_K_M` | SWE-agent tuned larger candidate | Deleted; too slow |
| 2 | `hf.co/Jackrong/Qwopus3.6-27B-Coder-GGUF:Q4_K_M` | Closest Claude-like coding candidate | Deleted untested after Qwen3-Coder passed |
| 3 | `hf.co/unsloth/rnj-1-instruct-GGUF:Q4_K_M` | Fast, cheap agentic sanity check | Tested; medium near miss |
| 4 | `hf.co/raicoon2k/Qwen3.5-9B-MTP-SWE-Agent-GGUF:Q4_K_M` | Small SWE-agent tuned Qwen variant | Queued |

## Testing Notes

- Do not judge a model from chat quality alone. Record direct sanity, tool-call behavior, edit behavior, test behavior, and final test result.
- A model that only prints plans or pseudo tool calls fails the agent benchmark.
- A model that can call tools but cannot inspect and repair test failures is not good enough for the first goal.
- Keep one model loaded at a time. Use the `qwen3-coder-30b-65k` alias as the current baseline; use 32k only when testing smaller or unknown candidates to reduce memory pressure.
- The default lean tool profile hides bulky non-coding tools but keeps core coding tools available. Use `--llama-tools full` only when testing whether a hidden tool is required, and `--llama-tools tiny` only for strict command-execution benchmarks.
- The wrapper advertises the configured context window to the CLI, but the proxy does not yet force Ollama `num_ctx`; confirm actual loaded context with `ollama ps`.
- Proxy parser fixes changed the results materially: mixed prose followed by bare JSON tool calls and XML-style `<tool name="..." function="..."/>` calls now translate into real function calls. Retest previously failed models only when the failure mode was tool-call formatting, not weak implementation.
- Ornith improved materially after hiding MCP/resource/plugin tools. A temporary stricter profile exposed only `exec_command`, but that may unfairly nerf coding runs because `write_stdin` is useful for long-running commands and interactive sessions.
- Ornith medium failure looks primarily model-side after the tool-surface patch: proxy logs showed only `exec_command` was exposed and backend requests completed, while the model generated incomplete/broken code. Direct Ollama prompting on the same medium fixture also failed to produce a usable implementation.
- `LLAMA_CODEX_CONTEXT_WINDOW=65536` improves the CLI-side budget, but Ollama `/v1/responses` ignores request-level context overrides. Use a model alias with `PARAMETER num_ctx 65536` when the backend must actually load a 65k context.
- Avoid retesting deleted Fable/Composer variants unless the wrapper changes to a different native Ollama tool protocol.
