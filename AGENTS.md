# Rules

## Local Model Testing

- Store tested model results in `local-model-test-backlog.md`.
- Use `models-testing-sandbox/` for repeatable benchmark fixtures and run copies.
- Treat 64k as the minimum advertised context window for `llama-codex` usability, but verify the actual loaded Ollama context with `ollama ps`.
- Test one model at a time. Stop or unload unrelated Ollama models before running a benchmark to avoid memory pressure and mixed results.
- Always start from a fresh fixture copy under `models-testing-sandbox/runs/<model>-<tier>/`. Do not judge a model from a reused or partially edited run directory.
- Run a direct exact-response sanity check before an agentic benchmark. A model that cannot answer a trivial exact `ok` prompt is not ready for coding-agent testing.
- Use the tiered fixtures consistently:
  - Easy: `models-testing-sandbox/benchmarks/easy-api`
  - Medium: `models-testing-sandbox/benchmarks/medium-task-library`
  - Hard: `models-testing-sandbox/benchmarks/hard-note-service`
- For each benchmark, require the model to edit files, run `python3 -m unittest discover -s tests -v`, and stop only when tests pass or a clear failure mode appears.
- Independently rerun the test command from the run directory before recording a pass.
- Record the full model tag, requested context, actual loaded context, direct sanity result, tool-call behavior, edit/test behavior, final test result, and decision.

## Failure Classification

- Important: If its fixable on our end, patch the code, rerun the benchmark and see if it passes. 
- Direct-following failure: the model cannot satisfy the direct exact-response sanity check.
- Proxy/template failure: direct Ollama generation works, but `llama-codex` fails before model work because the proxy/runtime payload is rejected.
- Tool-compatibility failure: the model emits invalid tool calls, pseudo tool calls, or session-control calls with bogus process IDs.
- Edit failure: the model uses tools but does not make coherent implementation changes.
- Test-repair failure: the model edits and runs tests but cannot diagnose or repair remaining failures.
- Tier pass: a fresh run directory passes the benchmark in an independent verification command.

## Tool Surface

- Keep irrelevant integration tools hidden during local model tests, especially MCP/resource discovery and plugin-install tools.
- Do not over-restrict core coding tools when judging model quality. If a stricter profile is used, record it because results are not directly comparable.
- Separate model quality from wrapper behavior. If a model fails because of a proxy/template/runtime issue, mark it as blocked rather than bad.
