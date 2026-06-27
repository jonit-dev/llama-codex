.PHONY: install test status stop clean

install:
	./install.sh

test:
	python3 -m py_compile src/ollama_codex_proxy.py
	python3 tests/test_proxy_parser.py
	bash -n bin/llama-codex install.sh

status:
	./bin/llama-codex --llama-status

stop:
	./bin/llama-codex --llama-stop

clean:
	rm -rf src/__pycache__ tests/__pycache__ .pytest_cache
