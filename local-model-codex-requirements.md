# Local Model Requirements for `llama-codex`

This document captures the minimum bar for local models before spending time on full `llama-codex` benchmarks. The goal is to avoid testing models that can chat about code but cannot complete the agent loop: inspect files, edit the right implementation, run tests, diagnose failures, and repair the result.

## Minimum Bar

A model should not be treated as a serious `llama-codex` candidate unless it meets all of these requirements.

1. **Direct instruction following**
   - Must answer a trivial exact-response prompt with only the requested token.
   - Leading/trailing whitespace is a warning sign; extra prose, markup, or role/channel text is a failure.

2. **Compatible tool use**
   - Must emit real tool calls that the wrapper can execute.
   - Must not print pseudo tool calls as text.
   - Must not invent session IDs, process IDs, tool names, or shell-control actions.

3. **File-edit discipline**
   - Must modify repository files, not only describe patches in chat.
   - Must edit the file implicated by the failing test or traceback.
   - Must avoid shell-quoting artifacts, malformed Python, and broad rewrites unrelated to the failure.

4. **Test loop competence**
   - Must run the required test command.
   - Must read failures and repair the cause, not repeat the same edit.
   - Must stop only after tests pass or after a clear, classifiable blocker.

5. **Medium-tier competence**
   - Easy-tier success is not enough.
   - A useful coding-agent model must pass the medium task-library benchmark, because it exercises multi-file coordination, domain modeling, validation, filtering, persistence, and test repair.

6. **Practical runtime**
   - Must run without CPU spill or severe memory pressure on the target machine.
   - Must load the requested context in `ollama ps`; advertised context is not enough.
   - For this repo, 64k actual context is the practical baseline for serious testing.

## Benchmark Gate

Use this sequence before spending time on hard benchmarks:

1. Pull or create the model alias.
2. Confirm only one model is loaded.
3. Run direct exact-response sanity.
4. Confirm actual loaded context with `ollama ps`.
5. Run the medium benchmark from a fresh copy:

```sh
models-testing-sandbox/benchmarks/medium-task-library
python3 -m unittest discover -s tests -v
```

6. Independently rerun the test command from the run directory.
7. Record the model tag, requested context, actual context, tool behavior, edit behavior, test behavior, and final decision.

Do not move to hard unless medium passes independently.

## Failure Patterns Seen So Far

### Direct-Following Failure

Some models fail before agent testing because they cannot answer a trivial exact prompt. Common bad outputs include channel markup, explanations, markdown, or multiple tokens. These models are not worth benchmarking until their template/runtime path changes.

### Pseudo-Tool Failure

Some models understand that tools exist but print tool-shaped text instead of making callable tool requests. This is a hard failure for `llama-codex` unless a parser/runtime change specifically targets that format.

### Chat-Only Implementation Failure

Some models read the files, then return code in the final message without editing files or running tests. This fails the benchmark even if the proposed code looks plausible.

### Broken Edit Failure

Weak models may make real edits but introduce syntax errors, missing imports, invalid persistence logic, or shell-quoting artifacts. If they cannot repair those errors from test output, they are not useful as coding agents.

### Test-Repair Failure

The most important failure class is a model that can inspect, edit, and run tests but cannot use the traceback to fix the right cause. The Qwen3.5 9B SWE-agent run is the current example: it read the medium tests, edited files, ran tests, then repeatedly failed to repair simple `NameError` and state-management issues correctly.

## Model Size Guidance

Small agent-tuned models are not automatically useful. A 7B-10B model may call tools correctly but still lack the repair ability needed for multi-file work.

Current practical expectations:

- **7B-10B:** Only useful as cheap baselines unless they pass medium. Do not assume SWE-agent tuning is enough.
- **14B-24B:** Worth testing only if direct sanity and tool calls are clean.
- **30B-40B or efficient MoE:** Current sweet spot for this machine if the model loads mostly on GPU and supports 64k context.
- **Very large MoE at low quant:** Worth exploring, but low quantization may erase the reasoning gains. Require medium pass before spending hard-tier time.

## Current Baseline

`qwen3-coder-30b-65k` is the current baseline because it passed the medium benchmark and the hard note-service benchmark with real tool use, file edits, test execution, failure repair, and independent verification at actual Ollama `CONTEXT 65536`.

Any new model should be compared against that behavior, not just against direct chat quality or easy-tier success.

## Decision Rules

- Delete or deprioritize models that fail direct exact-response sanity.
- Delete or deprioritize models that cannot make real tool calls.
- Do not retest a model unless the failure mode matches a wrapper/runtime fix.
- Do not count easy-tier pass as enough for repo work.
- Do not count a run as passed until an independent verification command succeeds.
- Prefer one strong baseline model over a queue of small models that repeatedly fail medium.
