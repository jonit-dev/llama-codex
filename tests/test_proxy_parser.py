import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("proxy", ROOT / "src" / "ollama_codex_proxy.py")
proxy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(proxy)


def test_parse_qwen_tool_call_suffix():
    parsed = proxy.parse_tool_text(
        '{"name": "exec_command", "arguments": {"cmd": "pwd"}}\n</tool_call>',
        {"exec_command"},
    )
    assert parsed == ("exec_command", '{"cmd": "pwd"}')


def test_ignores_disallowed_tool():
    parsed = proxy.parse_tool_text(
        '{"name": "unknown", "arguments": {"cmd": "pwd"}}\n</tool_call>',
        {"exec_command"},
    )
    assert parsed is None


def test_api_tags_reports_context_window():
    metadata = proxy.model_metadata("model-a", 8192)
    assert metadata["models"][0]["slug"] == "model-a"
    assert metadata["models"][0]["context_window"] == 8192


if __name__ == "__main__":
    test_parse_qwen_tool_call_suffix()
    test_ignores_disallowed_tool()
    test_api_tags_reports_context_window()
    print("proxy parser tests passed")
