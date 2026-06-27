# llama-codex

Use Codex normally, but route model calls to a local Ollama model.

Day to day, run it exactly like `codex`:

```sh
llama-codex --yolo
```

Everything else is still the Codex interface:

```sh
llama-codex
llama-codex --yolo
llama-codex exec "Fix the failing tests"
llama-codex -a never exec "Fix the failing tests"
```

Behind the scenes, `llama-codex` starts Ollama when needed, starts a small compatibility proxy, writes a temporary model catalog, and delegates to the real `codex` binary.

## Setup

```sh
/Users/jsilva3/projects/llama-codex/install.sh
llama-codex init
```

`install.sh` creates:

```sh
~/.local/bin/llama-codex
```

`llama-codex init` verifies required commands, starts Ollama, pulls the default model if missing, writes the temporary model catalog, starts the compatibility proxy, and runs `doctor`.

Before `init`, make sure these are installed:

```text
codex
ollama
python3
curl
```

If a dependency is missing, `init` offers to install supported dependencies:

```sh
llama-codex init
```

For unattended setup:

```sh
llama-codex init --yes
```

Supported installers:

```text
codex   npm install -g @openai/codex
ollama  brew install ollama
python3 brew install python
curl    brew install curl
```

## Default Model

By default, `llama-codex` uses:

```text
hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:UD-Q4_K_XL
```

So this is enough:

```sh
cd /path/to/project
llama-codex --yolo
```

## Advanced

Use any Ollama model name that supports the API shape Codex needs:

```sh
llama-codex --yolo -m hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:UD-Q4_K_XL
```

Or use environment variables:

```sh
LLAMA_CODEX_MODEL='hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:UD-Q4_K_XL' \
LLAMA_CODEX_CONTEXT_WINDOW=32768 \
llama-codex --yolo
```

The default context window is `8192` tokens. This keeps local runs less likely to put the machine under heavy memory pressure.

Set a larger context for the proxy/model catalog when needed:

```sh
llama-codex --llama-context 32768 --yolo
```

On memory-constrained machines, lower it again if the desktop becomes sluggish or unstable:

```sh
llama-codex --llama-context 8192 --yolo
```

When `llama-codex` starts Ollama, it uses conservative Ollama settings by default:

```text
OLLAMA_NUM_PARALLEL=1
OLLAMA_MAX_LOADED_MODELS=1
```

Override those with wrapper-specific environment variables:

```sh
LLAMA_CODEX_OLLAMA_NUM_PARALLEL=1 \
LLAMA_CODEX_OLLAMA_MAX_LOADED_MODELS=1 \
llama-codex --yolo
```

## Extra Wrapper Flags

These flags are consumed by `llama-codex` and are not passed to Codex:

```sh
--llama-model MODEL
--llama-context TOKENS
--llama-status
--llama-restart
--llama-stop
--llama-help
```

Everything else is passed through to `codex`.

Check resolved wrapper config:

```sh
llama-codex --llama-status
```

Verify setup:

```sh
llama-codex doctor
```

Stop the compatibility proxy:

```sh
llama-codex --llama-stop
```

Run local project checks:

```sh
make test
```

## Current Limitations

- This is a compatibility shim, not a quality guarantee.
- Qwen3-Coder can run at 32k context on the M1 Pro 32 GB machine, but that setting can put heavy pressure on local memory and GPU resources. The default is 8k for safer day-to-day use.
- Qwen2.5-Coder 14B and Seed-Coder 8B were removed after failing the local Codex workflow.
- The proxy rewrites some model-emitted JSON tool text into Codex function calls.
- Model support is empirical. Some Ollama models do not support tools, and some emit tool-call text Codex cannot execute without parser support.

## Files

```text
bin/llama-codex              wrapper CLI
src/ollama_codex_proxy.py    compatibility proxy
install.sh                   symlink installer
tests/test_proxy_parser.py   parser smoke tests
```
