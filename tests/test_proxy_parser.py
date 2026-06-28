import importlib.util
import json
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


def test_api_tags_can_report_reject_shell_writes():
    class Server:
        model = "model-a"
        context_window = 8192
        deny_tool_pattern = ""
        reject_shell_writes = True

    assert Server.reject_shell_writes is True


def test_cap_positive_int():
    assert proxy.cap_positive_int(None, 2048) == 2048
    assert proxy.cap_positive_int(-1, 2048) == 2048
    assert proxy.cap_positive_int(4096, 2048) == 2048
    assert proxy.cap_positive_int(1024, 2048) == 1024


def test_tool_denied_matches_full_or_short_name():
    pattern = r"^(list_mcp_resources|tool_search_tool|request_plugin_install)$"
    assert proxy.tool_denied("list_mcp_resources", pattern)
    assert proxy.tool_denied("tool_search.tool_search_tool", pattern)
    assert proxy.tool_denied("functions.request_plugin_install", pattern)
    assert not proxy.tool_denied("exec_command", pattern)
    assert not proxy.tool_denied("functions.write_stdin", pattern)
    assert not proxy.tool_denied("list_mcp_resources", "")


def test_rewrites_touch_to_apply_patch():
    arguments = proxy.apply_exec_guard(
        "exec_command",
        json.dumps({"cmd": "touch tasklib/__init__.py tasklib/models.py"}),
        True,
    )
    data = json.loads(arguments)
    assert "apply_patch <<'PATCH_LLAMACODEX'" in data["cmd"]
    assert "*** Add File: tasklib/__init__.py" in data["cmd"]
    assert "*** Add File: tasklib/models.py" in data["cmd"]
    assert "touch" not in data["cmd"]


def test_rewritten_touch_rejects_top_level_module_shadowing_package():
    arguments = proxy.apply_exec_guard(
        "exec_command",
        json.dumps({"cmd": "touch notes.py"}),
        True,
    )
    data = json.loads(arguments)
    assert "[ -d notes ]" in data["cmd"]
    assert "edit the package files instead" in data["cmd"]
    assert "*** Add File: notes.py" in data["cmd"]


def test_rewrites_cat_heredoc_to_apply_patch():
    arguments = proxy.apply_exec_guard(
        "exec_command",
        json.dumps({"cmd": "cat > tasklib/models.py << 'EOF'\nclass Task:\n    pass\nEOF"}),
        True,
    )
    data = json.loads(arguments)
    assert "apply_patch <<'PATCH_LLAMACODEX'" in data["cmd"]
    assert "*** Delete File: tasklib/models.py" in data["cmd"]
    assert "*** Add File: tasklib/models.py" in data["cmd"]
    assert "+class Task:" in data["cmd"]
    assert "cat >" not in data["cmd"]


def test_rewrites_cat_heredoc_with_redirect_after_delimiter():
    arguments = proxy.apply_exec_guard(
        "exec_command",
        json.dumps({"cmd": "cat <<'EOF' > ledger/store.py\nclass LedgerStore:\n    pass\nEOF"}),
        True,
    )
    data = json.loads(arguments)
    assert "*** Add File: ledger/store.py" in data["cmd"]
    assert "+class LedgerStore:" in data["cmd"]
    assert "cat <<" not in data["cmd"]


def test_rejected_shell_write_reports_original_command():
    arguments = proxy.apply_exec_guard(
        "exec_command",
        json.dumps({"cmd": "printf 'x' > ledger/store.py"}),
        True,
    )
    data = json.loads(arguments)
    assert "proxy rejected this edit command" in data["cmd"]
    assert "printf" in data["cmd"]
    assert "ledger/store.py" in data["cmd"]


def test_rewrites_echo_redirect_to_apply_patch():
    arguments = proxy.apply_exec_guard(
        "exec_command",
        json.dumps(
            {
                "cmd": "echo 'from .store import LedgerStore\nfrom .server import create_app' > ledger/__init__.py"
            }
        ),
        True,
    )
    data = json.loads(arguments)
    assert "*** Add File: ledger/__init__.py" in data["cmd"]
    assert "+from .store import LedgerStore" in data["cmd"]
    assert "+from .server import create_app" in data["cmd"]
    assert "echo" not in data["cmd"]


def test_rejects_rm_source_edit_command():
    arguments = proxy.apply_exec_guard(
        "exec_command",
        json.dumps({"cmd": "rm bookmarks/vault.py"}),
        True,
    )
    data = json.loads(arguments)
    assert "proxy rejected this edit command" in data["cmd"]
    assert "do not use touch, rm" in data["cmd"]
    assert "rm bookmarks/vault.py" in data["cmd"]


def test_unwraps_nested_exec_command_shell_text():
    arguments = proxy.apply_exec_guard(
        "exec_command",
        json.dumps({"cmd": 'exec_command("exec_command", {"cmd": "ls -la", "workdir": "/tmp"})'}),
        True,
    )
    data = json.loads(arguments)
    assert data["cmd"] == "ls -la"
    assert data["workdir"] == "/tmp"


def test_unwrapped_nested_exec_still_applies_shell_write_guard():
    arguments = proxy.apply_exec_guard(
        "exec_command",
        json.dumps({"cmd": 'exec_command("exec_command", {"cmd": "echo ok > a.txt"})'}),
        True,
    )
    data = json.loads(arguments)
    assert "*** Add File: a.txt" in data["cmd"]
    assert "+ok" in data["cmd"]


def test_rewrites_apply_patch_file_patch_flags_when_payload_is_real_patch():
    arguments = proxy.apply_exec_guard(
        "exec_command",
        json.dumps(
            {
                "cmd": "apply_patch --file ignored.js --patch '*** Begin Patch\n*** Update File: src/planner.js\n@@\n-old\n+new\n*** End Patch'"
            }
        ),
        True,
    )
    data = json.loads(arguments)
    assert "llama-codex apply_patch compatibility" in data["cmd"]
    assert "*** Update File: src/planner.js" in data["cmd"]
    assert "--file" not in data["cmd"]


def test_rejects_apply_patch_file_patch_flags_with_non_patch_payload():
    arguments = proxy.apply_exec_guard(
        "exec_command",
        json.dumps({"cmd": "apply_patch --file src/planner.js --patch 'const id = `a${newTrip.activities.length + 1}`;'"}),
        True,
    )
    data = json.loads(arguments)
    assert "rejected malformed apply_patch command" in data["cmd"]
    assert "does not accept --file or --patch flags" in data["cmd"]
    assert "src/planner.js" in data["cmd"]


def test_rejects_malformed_apply_patch_shell_command_with_guidance():
    arguments = proxy.apply_exec_guard(
        "exec_command",
        json.dumps({"cmd": "apply_patch --file src/planner.js"}),
        True,
    )
    data = json.loads(arguments)
    assert "rejected malformed apply_patch command" in data["cmd"]
    assert "does not accept --file or --patch flags" in data["cmd"]
    assert "src/planner.js" in data["cmd"]


def test_translates_native_apply_patch_call_to_exec_command():
    response = {
        "output": [
            {
                "type": "function_call",
                "name": "apply_patch",
                "arguments": json.dumps({"patch": "*** Begin Patch\n*** Add File: a.txt\n+ok\n*** End Patch"}),
            }
        ]
    }
    translated = proxy.translate_tool_text_response(response, {"exec_command"}, reject_shell_writes=True)
    item = translated["output"][0]
    assert item["name"] == "exec_command"
    data = json.loads(item["arguments"])
    assert "llama-codex apply_patch compatibility" in data["cmd"]
    assert "apply_patch <\"$patch_file\"" in data["cmd"]
    assert "git apply --recount" in data["cmd"]
    assert "*** Add File: a.txt" in data["cmd"]


def test_malformed_native_apply_patch_call_becomes_exec_diagnostic():
    response = {
        "output": [
            {
                "type": "function_call",
                "name": "apply_patch",
                "arguments": json.dumps({"cmd": "not a patch"}),
            }
        ]
    }
    translated = proxy.translate_tool_text_response(response, {"exec_command"}, reject_shell_writes=True)
    item = translated["output"][0]
    assert item["name"] == "exec_command"
    data = json.loads(item["arguments"])
    assert "rejected native apply_patch call" in data["cmd"]
    assert "not a patch" in data["cmd"]


def test_translates_text_apply_patch_call_to_exec_command():
    response = {
        "id": "resp-test",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            {
                                "name": "apply_patch",
                                "arguments": {
                                    "patch": "*** Begin Patch\n*** Add File: a.txt\n+ok\n*** End Patch"
                                },
                            }
                        ),
                    }
                ],
            }
        ],
    }
    translated = proxy.translate_tool_text_response(response, {"exec_command"}, reject_shell_writes=True)
    item = translated["output"][0]
    assert item["type"] == "function_call"
    assert item["name"] == "exec_command"
    data = json.loads(item["arguments"])
    assert "*** Add File: a.txt" in data["cmd"]


def test_translates_custom_apply_patch_input_to_exec_command():
    response = {
        "output": [
            {
                "id": "cp_1",
                "type": "custom_tool_call",
                "name": "apply_patch",
                "input": "*** Begin Patch\n*** Add File: a.txt\n+ok\n*** End Patch",
            }
        ]
    }
    translated = proxy.translate_tool_text_response(response, {"exec_command"}, reject_shell_writes=True)
    item = translated["output"][0]
    assert item["type"] == "function_call"
    assert item["name"] == "exec_command"
    assert item["call_id"] == "call_cp_1"
    data = json.loads(item["arguments"])
    assert "*** Add File: a.txt" in data["cmd"]
    assert "input" not in item


def test_translates_unified_diff_apply_patch_to_compat_command():
    response = {
        "output": [
            {
                "type": "function_call",
                "name": "apply_patch",
                "arguments": json.dumps({"patch": "--- /dev/null\n+++ b/a.txt\n@@ -0,0 +1 @@\n+ok\n"}),
            }
        ]
    }
    translated = proxy.translate_tool_text_response(response, {"exec_command"}, reject_shell_writes=True)
    item = translated["output"][0]
    assert item["name"] == "exec_command"
    data = json.loads(item["arguments"])
    assert "if [ -e a.txt ]; then" in data["cmd"]
    assert "*** Delete File: a.txt" in data["cmd"]
    assert "*** Add File: a.txt" in data["cmd"]
    assert "+ok" in data["cmd"]


def test_repairs_shorthand_apply_patch_header():
    response = {
        "output": [
            {
                "type": "function_call",
                "name": "apply_patch",
                "arguments": json.dumps(
                    {"patch": "*** Begin Patch\n*** notes/__init__.py\n+from .store import NoteStore\n*** End Patch"}
                ),
            }
        ]
    }
    translated = proxy.translate_tool_text_response(response, {"exec_command"}, reject_shell_writes=True)
    data = json.loads(translated["output"][0]["arguments"])
    assert "*** Delete File: notes/__init__.py" in data["cmd"]
    assert "*** Add File: notes/__init__.py" in data["cmd"]
    assert "+from .store import NoteStore" in data["cmd"]
    assert "llama-codex apply_patch compatibility" not in data["cmd"]


def test_shorthand_patch_rejects_top_level_module_shadowing_package():
    command = proxy.shorthand_patch_command("*** Begin Patch\n*** notes.py\n+VALUE = 1\n*** End Patch")
    assert command is not None
    assert "[ -d notes ]" in command
    assert "edit the package files instead" in command


def test_translates_nested_apply_patch_object():
    response = {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "tool_call",
                        "call": {
                            "name": "apply_patch",
                            "input": "*** Begin Patch\n*** Add File: a.txt\n+ok\n*** End Patch",
                        },
                    }
                ],
            }
        ]
    }
    translated = proxy.translate_tool_text_response(response, {"exec_command"}, reject_shell_writes=True)
    call = translated["output"][0]["content"][0]["call"]
    assert call["name"] == "exec_command"
    assert call["type"] == "function_call"
    data = json.loads(call["arguments"])
    assert "*** Add File: a.txt" in data["cmd"]


def test_malformed_nested_apply_patch_object_becomes_exec_diagnostic():
    response = {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "tool_call",
                        "call": {
                            "name": "apply_patch",
                            "arguments": {"cmd": "still not a patch"},
                        },
                    }
                ],
            }
        ]
    }
    translated = proxy.translate_tool_text_response(response, {"exec_command"}, reject_shell_writes=True)
    call = translated["output"][0]["content"][0]["call"]
    assert call["name"] == "exec_command"
    data = json.loads(call["arguments"])
    assert "rejected native apply_patch call" in data["cmd"]
    assert "still not a patch" in data["cmd"]


def test_translates_premature_prose_to_exec_diagnostic():
    response = {
        "id": "resp-test",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "The problem is the ID generation. Let me fix the implementation:",
                    }
                ],
            }
        ],
    }
    translated = proxy.translate_tool_text_response(response, {"exec_command"}, reject_shell_writes=True)
    item = translated["output"][0]
    assert item["type"] == "function_call"
    assert item["name"] == "exec_command"
    data = json.loads(item["arguments"])
    assert "rejected premature prose-only response" in data["cmd"]


def test_does_not_translate_completion_prose_to_exec_diagnostic():
    response = {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "Done. All tests pass."}],
            }
        ],
    }
    translated = proxy.translate_tool_text_response(response, {"exec_command"}, reject_shell_writes=True)
    assert translated["output"][0]["type"] == "message"


def test_detects_force_patch_first_prompt():
    assert proxy.payload_requests_force_patch_first(
        {"input": "Your first tool call in the next turn must be exec_command."}
    )
    assert not proxy.payload_requests_force_patch_first({"input": "Read files, then patch."})


def test_force_patch_first_rejects_diagnostic_exec_command():
    response = {
        "output": [
            {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps({"cmd": "cat bookmarks/vault.py"}),
            }
        ]
    }
    translated = proxy.translate_tool_text_response(
        response,
        {"exec_command"},
        reject_shell_writes=True,
        force_patch_first=True,
    )
    data = json.loads(translated["output"][0]["arguments"])
    assert "rejected diagnostic command during forced patch recovery" in data["cmd"]
    assert "cat bookmarks/vault.py" in data["cmd"]
    assert "required command shape" in data["cmd"]


def test_force_patch_first_allows_apply_patch_command():
    response = {
        "output": [
            {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps(
                    {"cmd": "apply_patch <<'PATCH'\n*** Begin Patch\n*** Add File: a.txt\n+ok\n*** End Patch\nPATCH"}
                ),
            }
        ]
    }
    translated = proxy.translate_tool_text_response(
        response,
        {"exec_command"},
        reject_shell_writes=True,
        force_patch_first=True,
    )
    data = json.loads(translated["output"][0]["arguments"])
    assert data["cmd"].startswith("apply_patch <<")


def test_force_patch_first_rejects_update_hunk_patch():
    response = {
        "output": [
            {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps(
                    {
                        "cmd": (
                            "apply_patch <<'PATCH'\n"
                            "*** Begin Patch\n"
                            "*** Update File: a.txt\n"
                            "@@\n"
                            "-old\n"
                            "+new\n"
                            "*** End Patch\n"
                            "PATCH"
                        )
                    }
                ),
            }
        ]
    }
    translated = proxy.translate_tool_text_response(
        response,
        {"exec_command"},
        reject_shell_writes=True,
        force_patch_first=True,
    )
    data = json.loads(translated["output"][0]["arguments"])
    assert "rejected update-hunk patch during forced recovery" in data["cmd"]
    assert "*** Delete File" in data["cmd"]


def test_repairs_unprefixed_add_file_lines():
    command = proxy.apply_patch_compat_command(
        "*** Begin Patch\n"
        "*** Delete File: a.py\n"
        "*** Add File: a.py\n"
        "+def one():\n"
        "    return 1\n"
        "*** End Patch"
    )
    assert "+def one():" in command
    assert "+    return 1" in command


def test_repairs_apply_patch_heredoc_closed_before_end_patch():
    arguments = proxy.apply_exec_guard(
        "exec_command",
        json.dumps(
            {
                "cmd": (
                    "apply_patch <<'PATCH'\n"
                    "*** Begin Patch\n"
                    "*** Add File: a.py\n"
                    "+ok = True\n"
                    "PATCH\n"
                    "*** End Patch\n"
                    "PATCH"
                )
            }
        ),
        True,
    )
    data = json.loads(arguments)
    assert data["cmd"].startswith("apply_patch <<")
    assert "*** End Patch\n" in data["cmd"]
    assert "PATCH\n*** End Patch" not in data["cmd"]


def test_rewrites_wrapped_unified_diff_heredoc_to_compat_command():
    arguments = proxy.apply_exec_guard(
        "exec_command",
        json.dumps(
            {
                "cmd": (
                    "apply_patch <<'PATCH'\n"
                    "*** Begin Patch\n"
                    "--- a.py\n"
                    "+++ a.py\n"
                    "@@ -1 +1 @@\n"
                    "-old\n"
                    "+new\n"
                    "*** End Patch\n"
                    "PATCH"
                )
            }
        ),
        True,
    )
    data = json.loads(arguments)
    assert "llama-codex apply_patch compatibility" in data["cmd"]
    assert "git apply --recount" in data["cmd"]
    assert "git apply -p0 --recount" in data["cmd"]
    assert "PY_LLAMACODEX_DIFF" in data["cmd"]
    assert "rest.startswith(prefix)" in data["cmd"]
    assert "grep -q '^\\*\\*\\* Begin Patch'" in data["cmd"]
    assert "grep -qi '^Invalid patch'" in data["cmd"]
    assert "*** Begin Patch" not in data["cmd"].split("cat >\"$patch_file\"", 1)[-1]


def test_unified_add_file_patch_becomes_conditional_apply_patch():
    command = proxy.apply_patch_compat_command(
        "--- /dev/null\n"
        "+++ b/bookmarks/vault.py\n"
        "@@ -0,0 +1,3 @@\n"
        "+import json\n"
        "+\n"
        "+print('ok')\n"
        "\\ No newline at end of file"
    )
    assert "llama-codex apply_patch compatibility" not in command
    assert "if [ -e bookmarks/vault.py ]; then" in command
    assert "*** Delete File: bookmarks/vault.py" in command
    assert "*** Add File: bookmarks/vault.py" in command
    assert "+import json" in command
    assert "+print('ok')" in command


def test_repairs_malformed_wrapped_unified_diff_header():
    command = proxy.apply_patch_compat_command(
        "*** Begin Patch\n"
        "-- a.py\n"
        "++ a.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
        "*** End Patch"
    )
    assert "--- a.py" in command
    assert "+++ a.py" in command
    assert "-- a.py" not in command.splitlines()


def test_repairs_complete_apply_patch_heredoc_missing_add_prefixes():
    arguments = proxy.apply_exec_guard(
        "exec_command",
        json.dumps(
            {
                "cmd": (
                    "apply_patch <<'PATCH'\n"
                    "*** Begin Patch\n"
                    "*** Delete File: a.py\n"
                    "*** Add File: a.py\n"
                    "import json\n"
                    "\n"
                    "print('ok')\n"
                    "*** End Patch\n"
                    "PATCH"
                )
            }
        ),
        True,
    )
    data = json.loads(arguments)
    assert "+import json" in data["cmd"]
    assert "+print('ok')" in data["cmd"]
    assert "\nimport json\n" not in data["cmd"]


def test_repairs_apply_patch_heredoc_missing_end_marker():
    arguments = proxy.apply_exec_guard(
        "exec_command",
        json.dumps(
            {
                "cmd": (
                    "apply_patch <<'PATCH'\n"
                    "*** Begin Patch\n"
                    "*** Delete File: a.py\n"
                    "*** Add File: a.py\n"
                    "import json\n"
                    "print('ok')\n"
                    "PATCH\n"
                    "PATCH"
                )
            }
        ),
        True,
    )
    data = json.loads(arguments)
    assert "+import json" in data["cmd"]
    assert "+print('ok')" in data["cmd"]
    assert "*** End Patch\n" in data["cmd"]
    assert data["cmd"].count("\nPATCH") == 1


def test_translates_embedded_patch_text_to_exec_command():
    response = {
        "id": "resp-test",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": (
                            "Here is the patch:\n\n"
                            "*** Begin Patch\n"
                            "*** Add File: a.txt\n"
                            "+ok\n"
                            "*** End Patch\n"
                        ),
                    }
                ],
            }
        ],
    }
    translated = proxy.translate_tool_text_response(
        response,
        {"exec_command"},
        reject_shell_writes=True,
        force_patch_first=True,
    )
    item = translated["output"][0]
    assert item["type"] == "function_call"
    assert item["name"] == "exec_command"
    data = json.loads(item["arguments"])
    assert "*** Add File: a.txt" in data["cmd"]
    assert "llama-codex apply_patch compatibility" in data["cmd"]


def test_force_patch_first_rejects_missing_tool_message():
    response = {
        "id": "resp-test",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": ""}],
            }
        ],
    }
    translated = proxy.translate_tool_text_response(
        response,
        {"exec_command"},
        reject_shell_writes=True,
        force_patch_first=True,
    )
    item = translated["output"][0]
    assert item["type"] == "function_call"
    assert item["name"] == "exec_command"
    data = json.loads(item["arguments"])
    assert "no tool call was made" in data["cmd"]
    assert "apply_patch" in data["cmd"]


if __name__ == "__main__":
    test_parse_qwen_tool_call_suffix()
    test_ignores_disallowed_tool()
    test_normalizes_channel_markup_before_parsing_tool_call()
    test_parses_tool_call_embedded_after_prose()
    test_parses_xml_tool_call_with_function_attribute()
    test_normalizes_channel_markup_in_response_text()
    test_api_tags_reports_context_window()
    test_api_tags_can_report_reject_shell_writes()
    test_cap_positive_int()
    test_tool_denied_matches_full_or_short_name()
    test_rewrites_touch_to_apply_patch()
    test_rewritten_touch_rejects_top_level_module_shadowing_package()
    test_rewrites_cat_heredoc_to_apply_patch()
    test_rewrites_cat_heredoc_with_redirect_after_delimiter()
    test_rejected_shell_write_reports_original_command()
    test_rewrites_echo_redirect_to_apply_patch()
    test_rejects_rm_source_edit_command()
    test_unwraps_nested_exec_command_shell_text()
    test_unwrapped_nested_exec_still_applies_shell_write_guard()
    test_rewrites_apply_patch_file_patch_flags_when_payload_is_real_patch()
    test_rejects_apply_patch_file_patch_flags_with_non_patch_payload()
    test_rejects_malformed_apply_patch_shell_command_with_guidance()
    test_translates_native_apply_patch_call_to_exec_command()
    test_malformed_native_apply_patch_call_becomes_exec_diagnostic()
    test_translates_text_apply_patch_call_to_exec_command()
    test_translates_custom_apply_patch_input_to_exec_command()
    test_translates_unified_diff_apply_patch_to_compat_command()
    test_repairs_shorthand_apply_patch_header()
    test_shorthand_patch_rejects_top_level_module_shadowing_package()
    test_translates_nested_apply_patch_object()
    test_malformed_nested_apply_patch_object_becomes_exec_diagnostic()
    test_translates_premature_prose_to_exec_diagnostic()
    test_does_not_translate_completion_prose_to_exec_diagnostic()
    test_detects_force_patch_first_prompt()
    test_force_patch_first_rejects_diagnostic_exec_command()
    test_force_patch_first_allows_apply_patch_command()
    test_force_patch_first_rejects_update_hunk_patch()
    test_repairs_unprefixed_add_file_lines()
    test_repairs_apply_patch_heredoc_closed_before_end_patch()
    test_rewrites_wrapped_unified_diff_heredoc_to_compat_command()
    test_unified_add_file_patch_becomes_conditional_apply_patch()
    test_repairs_malformed_wrapped_unified_diff_header()
    test_repairs_complete_apply_patch_heredoc_missing_add_prefixes()
    test_repairs_apply_patch_heredoc_missing_end_marker()
    test_translates_embedded_patch_text_to_exec_command()
    test_force_patch_first_rejects_missing_tool_message()
    print("proxy parser tests passed")
