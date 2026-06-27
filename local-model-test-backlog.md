# Local Model Test Backlog

This backlog tracks local Ollama models tested for `llama-codex` agentic coding. The first acceptance target is simple: create or repair a tiny Python library/API implementation, run the provided tests, and verify they pass.

## Standard Benchmark

Fixture:
- Work from a fresh copy of `/tmp/llama-codex-model-bench/base`.
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

## Tested Models

| Model | Context | Direct Following | Tool Calls | Edit/Test Result | Decision |
| --- | ---: | --- | --- | --- | --- |
| `hf.co/unsloth/GLM-4.7-Flash-GGUF:UD-Q4_K_XL` | 32k/64k | Failed basic exact-response sanity | Not reliable | 64k failed with malformed/empty final; 32k was weak | Deleted; do not retry without a different template/runtime reason |
| `hf.co/yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M` | 32k | Failed exact-response sanity with channel markup | Failed | Printed pseudo tool calls as text; no edits; no tests | Deleted; do not retry |
| `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M` | 32k | Failed exact-response sanity with channel markup | Failed | Produced a plan and empty final; no edits; tests still failed at original `NotImplementedError` | Deleted; do not retry |
| `hf.co/bartowski/Qwen2.5-Coder-14B-Instruct-GGUF:Q4_K_M` | 32k | Passed exact `ok` sanity | Passed | Overwrote `api.py` with an invalid one-line server script, reran the same failing test, and did not recover | Installed but failed benchmark; only retry with a better prompt/protocol change |

## Observed But Not Yet Standardized

| Model | Note | Decision |
| --- | --- | --- |
| `hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:UD-Q4_K_XL` | Large local default candidate. User-observed behavior was poor for `llama-codex`; memory pressure is higher than 14B models. | Keep only until a replacement passes; avoid more ad hoc testing |

## Current Queue

| Priority | Model | Purpose | Status |
| ---: | --- | --- | --- |
| 1 | `hf.co/Mungert/SWE-agent-LM-32B-GGUF:Q4_K_M` | SWE-agent tuned larger candidate | Pull delegated to background worker |
| 2 | `hf.co/Jackrong/Qwopus3.6-27B-Coder-GGUF:Q4_K_M` | Closest Claude-like coding candidate | Queued |
| 3 | `hf.co/unsloth/rnj-1-instruct-GGUF:Q4_K_M` | Fast, cheap agentic sanity check | Queued |
| 4 | `hf.co/raicoon2k/Qwen3.5-9B-MTP-SWE-Agent-GGUF:Q4_K_M` | Small SWE-agent tuned Qwen variant | Queued |

## Testing Notes

- Do not judge a model from chat quality alone. Record direct sanity, tool-call behavior, edit behavior, test behavior, and final test result.
- A model that only prints plans or pseudo tool calls fails the agent benchmark.
- A model that can call tools but cannot inspect and repair test failures is not good enough for the first goal.
- Keep one model loaded at a time. Use 32k context for first-pass testing unless the model passes and needs a larger-context follow-up.
- Avoid retesting deleted Fable/Composer variants unless the wrapper changes to a different native Ollama tool protocol.
