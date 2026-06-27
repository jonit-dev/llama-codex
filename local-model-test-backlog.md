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
| `hf.co/bartowski/Qwen2.5-Coder-14B-Instruct-GGUF:Q4_K_M` | 32k | Passed exact `ok` sanity | Passed | Overwrote `api.py` with an invalid one-line server script, reran the same failing test, and did not recover | Installed but failed benchmark; only retry with a better prompt/protocol change |
| `hf.co/deepreinforce-ai/Ornith-1.0-9B-GGUF:Q4_K_M` | 32k loaded / 64k advertised | Passed exact `ok` sanity | Passed after reducing visible tools to `exec_command` | Easy tier passed. Medium tier failed: partial broken multi-file edits, repeated repository rewrites, left `TaskService` unimplemented, and never reached a useful test-repair loop. A direct non-Codex medium prompt mostly echoed the test file and stopped after 484 chars. | Default model for easy/local worker tasks only; not reliable for medium agentic coding |

## Observed But Not Yet Standardized

| Model | Note | Decision |
| --- | --- | --- |
| `hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:UD-Q4_K_XL` | Large local default candidate. User-observed behavior was poor for `llama-codex`; memory pressure is higher than 14B models. | Keep only until a replacement passes; avoid more ad hoc testing |
| `hf.co/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF:Q4_K_M` | Direct `/api/generate` sanity passed, but `llama-codex` proxy run failed before generation with Ollama template HTTP 500: conversation roles must alternate. | Blocked by proxy/template compatibility; revisit only if stronger candidates fail |
| `hf.co/Mungert/SWE-agent-LM-32B-GGUF:Q4_K_M` | Pulled successfully. | Ready for standardized benchmark; test carefully due memory pressure |
| `hf.co/unsloth/rnj-1-instruct-GGUF:Q4_K_M` | Pulled successfully. | Ready for standardized benchmark |

## Current Queue

| Priority | Model | Purpose | Status |
| ---: | --- | --- | --- |
| 1 | `hf.co/Mungert/SWE-agent-LM-32B-GGUF:Q4_K_M` | SWE-agent tuned larger candidate | Pulled; ready |
| 2 | `hf.co/Jackrong/Qwopus3.6-27B-Coder-GGUF:Q4_K_M` | Closest Claude-like coding candidate | Queued |
| 3 | `hf.co/unsloth/rnj-1-instruct-GGUF:Q4_K_M` | Fast, cheap agentic sanity check | Pulled; ready |
| 4 | `hf.co/raicoon2k/Qwen3.5-9B-MTP-SWE-Agent-GGUF:Q4_K_M` | Small SWE-agent tuned Qwen variant | Queued |

## Testing Notes

- Do not judge a model from chat quality alone. Record direct sanity, tool-call behavior, edit behavior, test behavior, and final test result.
- A model that only prints plans or pseudo tool calls fails the agent benchmark.
- A model that can call tools but cannot inspect and repair test failures is not good enough for the first goal.
- Keep one model loaded at a time. Use 32k context for first-pass testing unless the model passes and needs a larger-context follow-up.
- The default lean tool profile hides bulky non-coding tools but keeps core coding tools available. Use `--llama-tools full` only when testing whether a hidden tool is required, and `--llama-tools tiny` only for strict command-execution benchmarks.
- The wrapper advertises the configured context window to the CLI, but the proxy does not yet force Ollama `num_ctx`; confirm actual loaded context with `ollama ps`.
- Ornith improved materially after hiding MCP/resource/plugin tools. A temporary stricter profile exposed only `exec_command`, but that may unfairly nerf coding runs because `write_stdin` is useful for long-running commands and interactive sessions.
- Ornith medium failure looks primarily model-side after the tool-surface patch: proxy logs showed only `exec_command` was exposed and backend requests completed, while the model generated incomplete/broken code. Direct Ollama prompting on the same medium fixture also failed to produce a usable implementation.
- `LLAMA_CODEX_CONTEXT_WINDOW=65536` improved the CLI-side budget, but an Ollama `/v1/responses` check still loaded Ornith with `CONTEXT 32768`; changing actual backend context needs a separate proxy/runtime fix.
- Avoid retesting deleted Fable/Composer variants unless the wrapper changes to a different native Ollama tool protocol.
