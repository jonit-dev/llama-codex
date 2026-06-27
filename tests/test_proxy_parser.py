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


def test_normalizes_channel_markup_before_parsing_tool_call():
    parsed = proxy.parse_tool_text(
        '<|channel>thought\n<channel|>{"name": "exec_command", "arguments": {"cmd": "pwd"}}',
        {"exec_command"},
    )
    assert parsed == ("exec_command", '{"cmd": "pwd"}')


def test_parses_tool_call_embedded_after_prose():
    parsed = proxy.parse_tool_text(
        'I will inspect the file.\n\n{"name": "exec_command", "arguments": {"cmd": "cat README.md", "workdir": "/tmp"}}',
        {"exec_command"},
    )
    assert parsed == ("exec_command", '{"cmd": "cat README.md", "workdir": "/tmp"}')


def test_parses_xml_tool_call_with_function_attribute():
    parsed = proxy.parse_tool_text(
        '<tools>\n  <tool name="exec_command" function="{&quot;cmd&quot;:&quot;python3 -m unittest discover -s tests -v&quot;,&quot;workdir&quot;:&quot;/tmp&quot;}" />\n</tools>',
        {"exec_command"},
    )
    assert parsed == ("exec_command", '{"cmd": "python3 -m unittest discover -s tests -v", "workdir": "/tmp"}')


def test_normalizes_channel_markup_in_response_text():
    data = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "<|channel>thought\n<channel|>ok"},
                ],
            }
        ]
    }
    assert proxy.normalize_response_text(data)["output"][0]["content"][0]["text"] == "ok"


def test_api_tags_reports_context_window():
    metadata = proxy.model_metadata("model-a", 8192)
    assert metadata["models"][0]["slug"] == "model-a"
    assert metadata["models"][0]["context_window"] == 8192


def test_tool_denied_matches_full_or_short_name():
    pattern = r"^(list_mcp_resources|tool_search_tool|request_plugin_install)$"
    assert proxy.tool_denied("list_mcp_resources", pattern)
    assert proxy.tool_denied("tool_search.tool_search_tool", pattern)
    assert proxy.tool_denied("functions.request_plugin_install", pattern)
    assert not proxy.tool_denied("exec_command", pattern)
    assert not proxy.tool_denied("functions.write_stdin", pattern)
    assert not proxy.tool_denied("list_mcp_resources", "")


if __name__ == "__main__":
    test_parse_qwen_tool_call_suffix()
    test_ignores_disallowed_tool()
    test_normalizes_channel_markup_before_parsing_tool_call()
    test_parses_tool_call_embedded_after_prose()
    test_parses_xml_tool_call_with_function_attribute()
    test_normalizes_channel_markup_in_response_text()
    test_api_tags_reports_context_window()
    test_tool_denied_matches_full_or_short_name()
    print("proxy parser tests passed")
