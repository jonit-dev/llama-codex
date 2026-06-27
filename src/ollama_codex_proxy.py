#!/usr/bin/env python3
import argparse
import html
import json
import os
import re
import shlex
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def read_json(handler):
    length = int(handler.headers.get("content-length", "0"))
    body = handler.rfile.read(length) if length else b"{}"
    if not body:
        return {}
    return json.loads(body)


def model_metadata(model, context_window):
    return {
        "models": [
            {
                "slug": model,
                "display_name": model,
                "base_instructions": "",
                "context_window": context_window,
                "default_verbosity": "low",
                "experimental_supported_tools": [],
                "input_modalities": ["text"],
                "priority": 0,
                "shell_type": "default",
                "support_verbosity": True,
                "supported_in_api": True,
                "supported_reasoning_levels": [],
                "supports_parallel_tool_calls": False,
                "supports_reasoning_summaries": False,
                "truncation_policy": {"limit": 10000, "mode": "bytes"},
                "visibility": "list",
            }
        ]
    }


def cap_positive_int(value, cap):
    if not isinstance(value, int) or value <= 0:
        return cap
    return min(value, cap)


def parse_tool_text(text, allowed_names):
    text = normalize_model_text(text)
    candidates = []
    xml_tool_calls = []
    for match in re.finditer(
        r"<tool\s+[^>]*name=(['\"])(?P<name>.*?)\1[^>]*function=(['\"])(?P<function>.*?)\3\s*/?>",
        text,
        re.DOTALL,
    ):
        xml_tool_calls.append((html.unescape(match.group("name")), html.unescape(match.group("function"))))
    for match in re.finditer(r"<(?:tools?|tool_call)>\s*(\{.*?\})\s*</(?:tools?|tool_call)>", text, re.DOTALL):
        candidates.append(match.group(1))
    if "</tool_call>" in text:
        before_tool_end = text.split("</tool_call>", 1)[0]
        json_start = before_tool_end.find("{")
        if json_start >= 0:
            try:
                data, _ = json.JSONDecoder().raw_decode(before_tool_end[json_start:])
                candidates.append(json.dumps(data))
            except json.JSONDecodeError:
                pass
    for match in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL):
        candidates.append(match.group(1))
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        candidates.append(stripped)
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            data, _ = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "name" in data and "arguments" in data:
            candidates.append(json.dumps(data))

    for name, function_payload in xml_tool_calls:
        if name not in allowed_names:
            continue
        try:
            arguments = json.loads(function_payload)
        except json.JSONDecodeError:
            continue
        if isinstance(arguments, dict):
            return name, json.dumps(arguments)

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        name = data.get("name")
        arguments = data.get("arguments")
        if not name or name not in allowed_names or not isinstance(arguments, dict):
            continue
        return name, json.dumps(arguments)
    return None


def patch_delimiter(patch):
    base = "PATCH_LLAMACODEX"
    delimiter = base
    counter = 1
    while re.search(rf"^{re.escape(delimiter)}$", patch, re.MULTILINE):
        delimiter = f"{base}_{counter}"
        counter += 1
    return delimiter


def patch_file_line(path):
    if "\n" in path or path.startswith("-"):
        return None
    return path


def add_file_patch(path, content):
    file_line = patch_file_line(path)
    if file_line is None:
        return None
    lines = ["*** Begin Patch", f"*** Add File: {file_line}"]
    content_lines = content.splitlines()
    if not content_lines:
        lines.append("+")
    else:
        lines.extend(f"+{line}" for line in content_lines)
    lines.append("*** End Patch")
    return "\n".join(lines)


def replace_file_patch(path, content):
    file_line = patch_file_line(path)
    if file_line is None:
        return None
    add_patch = add_file_patch(path, content)
    if add_patch is None:
        return None
    return "\n".join(
        [
            "*** Begin Patch",
            f"*** Delete File: {file_line}",
            *add_patch.splitlines()[1:-1],
            "*** End Patch",
        ]
    )


def apply_patch_command(patch):
    delimiter = patch_delimiter(patch)
    return f"apply_patch <<'{delimiter}'\n{patch}\n{delimiter}"


def shorthand_patch_command(patch):
    lines = patch.splitlines()
    if len(lines) < 4:
        return None
    if lines[0].strip() != "*** Begin Patch" or lines[-1].strip() != "*** End Patch":
        return None
    match = re.fullmatch(r"\*\*\*\s+(?!Add File:|Delete File:|Update File:)(?P<path>\S.*)", lines[1].strip())
    if not match:
        return None
    content = []
    for line in lines[2:-1]:
        if not line.startswith("+"):
            return None
        content.append(line[1:])
    return conditional_apply_patch_command(match.group("path"), "\n".join(content))


def apply_patch_compat_command(patch):
    shorthand = shorthand_patch_command(patch)
    if shorthand:
        return shorthand
    delimiter = patch_delimiter(patch)
    return "\n".join(
        [
            "# llama-codex apply_patch compatibility",
            "patch_file=$(mktemp)",
            "clean_patch_file=$(mktemp)",
            f"cat >\"$patch_file\" <<'{delimiter}'",
            patch,
            delimiter,
            "sed '/^\\*\\*\\* /d' \"$patch_file\" >\"$clean_patch_file\"",
            "apply_patch <\"$patch_file\" || patch -p1 <\"$clean_patch_file\" || patch -p0 <\"$clean_patch_file\"",
            "rc=$?",
            "rm -f \"$patch_file\" \"$clean_patch_file\"",
            "exit $rc",
        ]
    )


def is_patch_text(value):
    if not isinstance(value, str):
        return False
    stripped = value.lstrip()
    return (
        stripped.startswith("*** Begin Patch")
        or stripped.startswith("diff --git ")
        or stripped.startswith("--- ")
    )


def extract_patch_argument(arguments):
    if is_patch_text(arguments):
        return arguments
    if isinstance(arguments, dict):
        data = arguments
    elif isinstance(arguments, str):
        try:
            data = json.loads(arguments)
        except json.JSONDecodeError:
            return None
    else:
        return None
    for key in ("patch", "input", "content", "text"):
        value = data.get(key)
        if is_patch_text(value):
            return value
    return None


def translate_apply_patch_call(name, arguments, allowed_names):
    if not name or name.rsplit(".", 1)[-1] != "apply_patch":
        return name, arguments
    exec_name = next((candidate for candidate in allowed_names if candidate.rsplit(".", 1)[-1] == "exec_command"), None)
    if not exec_name:
        return name, arguments
    patch = extract_patch_argument(arguments)
    if patch is None:
        return name, arguments
    return exec_name, json.dumps({"cmd": apply_patch_compat_command(patch)})


def translate_apply_patch_item(item, allowed_names):
    name = item.get("name")
    if not name or name.rsplit(".", 1)[-1] != "apply_patch":
        return False
    patch = extract_patch_argument(item.get("arguments"))
    if patch is None:
        patch = extract_patch_argument(item.get("input"))
    if patch is None:
        return False
    exec_name = next((candidate for candidate in allowed_names if candidate.rsplit(".", 1)[-1] == "exec_command"), None)
    if not exec_name:
        return False
    item["type"] = "function_call"
    item["name"] = exec_name
    item["arguments"] = json.dumps({"cmd": apply_patch_compat_command(patch)})
    item["status"] = item.get("status", "completed")
    item["call_id"] = item.get("call_id") or "call_" + item.get("id", "ollama_apply_patch").replace("-", "_")
    item.pop("input", None)
    return True


def translate_apply_patch_objects(value, allowed_names):
    if isinstance(value, list):
        for item in value:
            translate_apply_patch_objects(item, allowed_names)
        return value
    if not isinstance(value, dict):
        return value

    name = value.get("name")
    if isinstance(name, str) and name.rsplit(".", 1)[-1] == "apply_patch":
        translate_apply_patch_item(value, allowed_names)

    for child in list(value.values()):
        translate_apply_patch_objects(child, allowed_names)
    return value


def conditional_apply_patch_command(path, content):
    add_patch = add_file_patch(path, content)
    replace_patch = replace_file_patch(path, content)
    if add_patch is None or replace_patch is None:
        return None
    add_delimiter = patch_delimiter(add_patch)
    replace_delimiter = patch_delimiter(replace_patch)
    quoted_path = shlex.quote(path)
    guard = []
    if "/" not in path and path.endswith(".py"):
        package_dir = path[:-3]
        guard = [
            f"if [ ! -e {quoted_path} ] && [ -d {shlex.quote(package_dir)} ]; then",
            (
                "printf '%s\\n' "
                f"{shlex.quote(f'llama-codex proxy rejected creation of {path}: {package_dir}/ already exists; edit the package files instead.')} "
                ">&2; exit 2"
            ),
            "fi",
        ]
    return "\n".join(
        [
            *guard,
            f"if [ -e {quoted_path} ]; then",
            f"apply_patch <<'{replace_delimiter}'",
            replace_patch,
            replace_delimiter,
            "else",
            f"apply_patch <<'{add_delimiter}'",
            add_patch,
            add_delimiter,
            "fi",
        ]
    )


def unquote_shell_word(value):
    try:
        parts = shlex.split(value)
    except ValueError:
        return None
    if len(parts) != 1:
        return None
    return parts[0]


def rewrite_cat_heredoc(cmd):
    path_first = (
        r"\s*cat\s*>\s*(?P<path>(?:'[^']+'|\"[^\"]+\"|[^\s]+))"
        r"\s*<<\s*(?P<quote>['\"]?)(?P<delimiter>[A-Za-z_][A-Za-z0-9_-]*)\2"
        r"\s*\n(?P<body>.*)\n(?P=delimiter)\s*;?\s*$"
    )
    heredoc_first = (
        r"\s*cat\s*<<\s*(?P<quote>['\"]?)(?P<delimiter>[A-Za-z_][A-Za-z0-9_-]*)\1"
        r"\s*>\s*(?P<path>(?:'[^']+'|\"[^\"]+\"|[^\s]+))"
        r"\s*\n(?P<body>.*)\n(?P=delimiter)\s*;?\s*$"
    )
    match = re.match(path_first, cmd, re.DOTALL) or re.match(heredoc_first, cmd, re.DOTALL)
    if not match:
        return None
    path = unquote_shell_word(match.group("path"))
    if not path:
        return None
    return conditional_apply_patch_command(path, match.group("body"))


def rewrite_touch(cmd):
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return None
    if len(parts) < 2 or parts[0] != "touch":
        return None
    paths = [part for part in parts[1:] if not part.startswith("-")]
    if len(paths) != len(parts) - 1:
        return None
    commands = []
    for path in paths:
        patch = add_file_patch(path, "")
        if patch is None:
            return None
        delimiter = patch_delimiter(patch)
        if "/" not in path and path.endswith(".py"):
            package_dir = path[:-3]
            commands.extend(
                [
                    f"if [ ! -e {shlex.quote(path)} ] && [ -d {shlex.quote(package_dir)} ]; then",
                    (
                        "printf '%s\\n' "
                        f"{shlex.quote(f'llama-codex proxy rejected creation of {path}: {package_dir}/ already exists; edit the package files instead.')} "
                        ">&2; exit 2"
                    ),
                    "fi",
                ]
            )
        commands.extend(
            [
                f"if [ -e {shlex.quote(path)} ]; then",
                ":",
                "else",
                f"apply_patch <<'{delimiter}'",
                patch,
                delimiter,
                "fi",
            ]
        )
    return "\n".join(commands)


def rewrite_echo_redirect(cmd):
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return None
    if len(parts) != 4 or parts[0] != "echo" or parts[2] != ">":
        return None
    if parts[1].startswith("-"):
        return None
    return conditional_apply_patch_command(parts[3], parts[1])


def malformed_apply_patch_command(cmd):
    message = (
        "llama-codex proxy rejected malformed apply_patch command: use a heredoc like "
        "apply_patch <<'PATCH' ... PATCH; apply_patch does not accept --file or --patch flags."
    )
    rejected = f"llama-codex proxy rejected edit command: {cmd}"
    return (
        "printf '%s\\n' "
        f"{shlex.quote(message)} "
        f"{shlex.quote(rejected)} "
        ">&2; exit 2"
    )


def rewrite_apply_patch_shell_command(cmd):
    stripped = cmd.lstrip()
    if not stripped.startswith("apply_patch"):
        return None
    if re.match(r"^\s*apply_patch\s*(?:<<|<)\s*", cmd):
        return None
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return malformed_apply_patch_command(cmd)
    if not parts or parts[0] != "apply_patch":
        return None
    if len(parts) == 1:
        return malformed_apply_patch_command(cmd)
    if "--file" in parts or "--patch" in parts:
        try:
            path = parts[parts.index("--file") + 1]
            patch_or_content = parts[parts.index("--patch") + 1]
        except (ValueError, IndexError):
            return malformed_apply_patch_command(cmd)
        if is_patch_text(patch_or_content):
            return apply_patch_compat_command(patch_or_content)
        return malformed_apply_patch_command(cmd)
    if len(parts) == 2 and is_patch_text(parts[1]):
        return apply_patch_compat_command(parts[1])
    return malformed_apply_patch_command(cmd)


def rewrite_shell_write_command(cmd):
    return rewrite_cat_heredoc(cmd) or rewrite_echo_redirect(cmd) or rewrite_touch(cmd)


def extract_nested_exec_arguments(cmd):
    if not re.match(r"\s*(?:exec_command|[\w.]+\.exec_command)\s*\(", cmd):
        return None
    json_start = cmd.find("{")
    if json_start < 0:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(cmd[json_start:])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("cmd"), str):
        return None
    return data


def apply_exec_guard(name, arguments, reject_shell_writes):
    if not reject_shell_writes or not name:
        return arguments
    if name.rsplit(".", 1)[-1] != "exec_command":
        return arguments
    try:
        data = json.loads(arguments)
    except json.JSONDecodeError:
        return arguments
    if not isinstance(data, dict):
        return arguments
    cmd = data.get("cmd")
    if not isinstance(cmd, str):
        return arguments
    changed = False
    nested = extract_nested_exec_arguments(cmd)
    if nested is not None:
        data.update(nested)
        cmd = data["cmd"]
        changed = True
    stripped = cmd.lstrip()
    if "llama-codex apply_patch compatibility" in cmd:
        return arguments
    if stripped.startswith("apply_patch"):
        rewritten = rewrite_apply_patch_shell_command(cmd)
        if rewritten:
            data["cmd"] = rewritten
            return json.dumps(data)
        return arguments
    rewritten = rewrite_shell_write_command(cmd)
    if rewritten:
        data["cmd"] = rewritten
        return json.dumps(data)

    forbidden = re.compile(
        r"(^|[;&|]\s*)touch\b|"
        r"(^|[;&|]\s*)rm\s+|"
        r"(^|[;&|]\s*)unlink\s+|"
        r"\bcat\s*>|"
        r"\bcat\s*<<|"
        r"\btee\s+|"
        r"\bsed\s+-i\b|"
        r"\bperl\s+-i\b|"
        r">\s*[\w./~-]+|"
        r"\bpython3?\b.*\b(open|write_text)\s*\(",
        re.DOTALL,
    )
    if not forbidden.search(cmd):
        if changed:
            return json.dumps(data)
        return arguments
    rejected = f"llama-codex proxy rejected edit command: {cmd}"
    data["cmd"] = (
        "printf '%s\\n' "
        "'llama-codex proxy rejected this edit command: use apply_patch for file creation/modification; do not use touch, rm, cat >, tee, redirects, sed -i, perl -i, or Python file writes.' "
        f"{shlex.quote(rejected)} "
        ">&2; exit 2"
    )
    return json.dumps(data)


def force_patch_first_command(arguments):
    try:
        data = json.loads(arguments)
    except json.JSONDecodeError:
        return arguments
    if not isinstance(data, dict):
        return arguments
    cmd = data.get("cmd")
    if not isinstance(cmd, str):
        return arguments
    stripped = cmd.lstrip()
    if stripped.startswith("apply_patch") or "llama-codex apply_patch compatibility" in cmd:
        return arguments
    message = (
        "llama-codex proxy rejected diagnostic command during forced patch recovery: "
        "the first command must be an apply_patch heredoc that changes an implementation file."
    )
    rejected = f"rejected command: {cmd}"
    example = (
        "required command shape: apply_patch <<'PATCH'\\n"
        "*** Begin Patch\\n"
        "*** Delete File: path/to/file\\n"
        "*** Add File: path/to/file\\n"
        "+full corrected file line\\n"
        "*** End Patch\\n"
        "PATCH"
    )
    data["cmd"] = (
        "printf '%s\\n' "
        f"{shlex.quote(message)} "
        f"{shlex.quote(rejected)} "
        f"{shlex.quote(example)} "
        ">&2; exit 2"
    )
    return json.dumps(data)


def payload_requests_force_patch_first(value):
    if isinstance(value, dict):
        return any(payload_requests_force_patch_first(child) for child in value.values())
    if isinstance(value, list):
        return any(payload_requests_force_patch_first(child) for child in value)
    if not isinstance(value, str):
        return False
    normalized = " ".join(value.lower().split())
    return (
        "your first command in the next turn must be an apply_patch heredoc" in normalized
        or "first command must be an apply_patch" in normalized
    )


def premature_prose_command(text):
    if not isinstance(text, str):
        return None
    normalized = " ".join(text.lower().split())
    if not normalized:
        return None
    intent_patterns = (
        "let me fix",
        "i will fix",
        "i'll fix",
        "let me update",
        "i will update",
        "i'll update",
        "let me patch",
        "i will patch",
        "i'll patch",
        "the problem is",
        "the issue is",
    )
    if not any(pattern in normalized for pattern in intent_patterns):
        return None
    if any(done in normalized for done in ("tests pass", "verification passed", "all tests pass", "done")):
        return None
    message = (
        "llama-codex proxy rejected premature prose-only response: call exec_command with "
        "apply_patch or a verification command instead of saying what you will do."
    )
    return f"printf '%s\\n' {shlex.quote(message)} >&2; exit 2"


def normalize_model_text(text):
    if not isinstance(text, str):
        return text
    text = re.sub(r"<\|channel\>\s*thought\s*", "", text)
    text = re.sub(r"<channel\|>\s*", "", text)
    text = re.sub(r"</?channel>\s*", "", text)
    return text.strip()


def normalize_response_text(data):
    output = data.get("output")
    if not isinstance(output, list):
        return data
    for item in output:
        if item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                part["text"] = normalize_model_text(part["text"])
    return data


def translate_tool_text_response(data, allowed_names, reject_shell_writes=False, force_patch_first=False):
    data = normalize_response_text(data)
    translate_apply_patch_objects(data, allowed_names)
    output = data.get("output")
    if not isinstance(output, list):
        return data
    for index, item in enumerate(output):
        if translate_apply_patch_item(item, allowed_names):
            item["arguments"] = apply_exec_guard(item.get("name"), item["arguments"], reject_shell_writes)
            if force_patch_first:
                item["arguments"] = force_patch_first_command(item["arguments"])
            continue
        if item.get("type") == "function_call":
            name = item.get("name")
            arguments = item.get("arguments")
            if isinstance(arguments, str):
                name, arguments = translate_apply_patch_call(name, arguments, allowed_names)
                item["name"] = name
                item["arguments"] = apply_exec_guard(name, arguments, reject_shell_writes)
                if force_patch_first:
                    item["arguments"] = force_patch_first_command(item["arguments"])
            continue
        if item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        text = "".join(part.get("text", "") for part in content if part.get("type") == "output_text")
        parsed = parse_tool_text(text, set(allowed_names) | {"apply_patch"})
        if not parsed:
            exec_name = next((candidate for candidate in allowed_names if candidate.rsplit(".", 1)[-1] == "exec_command"), None)
            premature_command = premature_prose_command(text)
            if exec_name and premature_command:
                call_id = "call_" + item.get("id", data.get("id", "ollama")).replace("-", "_")
                output[index] = {
                    "id": "fc_" + call_id.removeprefix("call_"),
                    "type": "function_call",
                    "status": "completed",
                    "call_id": call_id,
                    "name": exec_name,
                    "arguments": json.dumps({"cmd": premature_command}),
                }
                return data
            continue
        name, arguments = parsed
        name, arguments = translate_apply_patch_call(name, arguments, allowed_names)
        arguments = apply_exec_guard(name, arguments, reject_shell_writes)
        if force_patch_first:
            arguments = force_patch_first_command(arguments)
        call_id = "call_" + item.get("id", data.get("id", "ollama")).replace("-", "_")
        output[index] = {
            "id": "fc_" + call_id.removeprefix("call_"),
            "type": "function_call",
            "status": "completed",
            "call_id": call_id,
            "name": name,
            "arguments": arguments,
        }
        return data
    return data


def sse_event(event, data):
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n".encode("utf-8")


def responses_sse(data):
    chunks = []
    created = dict(data)
    created["status"] = "in_progress"
    chunks.append(sse_event("response.created", {"type": "response.created", "response": created}))
    for index, item in enumerate(data.get("output", [])):
        chunks.append(sse_event("response.output_item.added", {"type": "response.output_item.added", "output_index": index, "item": item}))
        chunks.append(sse_event("response.output_item.done", {"type": "response.output_item.done", "output_index": index, "item": item}))
    chunks.append(sse_event("response.completed", {"type": "response.completed", "response": data}))
    return b"".join(chunks)


def tool_name(tool):
    if not isinstance(tool, dict):
        return None
    if tool.get("name"):
        return tool.get("name")
    function = tool.get("function")
    if isinstance(function, dict):
        return function.get("name")
    return None


def tool_denied(name, pattern):
    if not name or not pattern:
        return False
    short_name = name.rsplit(".", 1)[-1]
    return bool(re.search(pattern, name) or re.search(pattern, short_name))


class Proxy(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), fmt % args))

    def send_bytes(self, status, data, content_type="application/json"):
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status, data):
        self.send_bytes(status, json.dumps(data).encode("utf-8"))

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ("/v1/models", "/models"):
            self.send_json(200, model_metadata(self.server.model, self.server.context_window))
            return
        if path == "/api/tags":
            self.send_json(
                200,
                {
                    "models": [
                        {
                            "name": self.server.model,
                            "model": self.server.model,
                            "context_window": self.server.context_window,
                            "max_output_tokens": self.server.max_output_tokens,
                            "deny_tool_pattern": self.server.deny_tool_pattern,
                            "reject_shell_writes": self.server.reject_shell_writes,
                        }
                    ]
                },
            )
            return
        self.forward()

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == "/v1/responses":
            payload = read_json(self)
            payload["model"] = self.server.model
            if self.server.max_output_tokens > 0:
                payload["max_output_tokens"] = cap_positive_int(
                    payload.get("max_output_tokens"),
                    self.server.max_output_tokens,
                )
                payload["max_tokens"] = cap_positive_int(
                    payload.get("max_tokens"),
                    self.server.max_output_tokens,
                )
                options = payload.get("options")
                if not isinstance(options, dict):
                    options = {}
                options["num_predict"] = cap_positive_int(
                    options.get("num_predict"),
                    self.server.max_output_tokens,
                )
                payload["options"] = options
            stream_response = bool(payload.get("stream"))
            force_patch_first = payload_requests_force_patch_first(payload)
            payload["stream"] = False
            tools = payload.get("tools")
            allowed_tool_names = set()
            if isinstance(tools, list):
                before = len(tools)
                payload["tools"] = [
                    tool for tool in tools
                    if tool.get("type") == "function" and not tool_denied(tool_name(tool), self.server.deny_tool_pattern)
                ]
                allowed_tool_names = {name for name in (tool_name(tool) for tool in payload["tools"]) if name}
                if allowed_tool_names:
                    self.log_message("allowed function tools: %s", ",".join(sorted(allowed_tool_names)))
                removed_unsupported = sum(1 for tool in tools if tool.get("type") != "function")
                removed_denied = before - removed_unsupported - len(payload["tools"])
                if removed_unsupported:
                    self.log_message("removed %d unsupported non-function tool(s)", removed_unsupported)
                if removed_denied:
                    self.log_message("removed %d denied function tool(s)", removed_denied)
            self.forward(
                payload,
                allowed_tool_names=allowed_tool_names,
                stream_response=stream_response,
                force_patch_first=force_patch_first,
            )
            return
        self.forward(read_json(self))

    def forward(self, payload=None, allowed_tool_names=None, stream_response=False, force_patch_first=False):
        url = self.server.backend.rstrip("/") + self.path
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["content-type"] = "application/json"
        req = Request(url, data=data, headers=headers, method=self.command)
        try:
            with urlopen(req, timeout=None) as resp:
                body = resp.read()
                content_type = resp.headers.get("content-type", "application/json")
                if allowed_tool_names and "application/json" in content_type:
                    try:
                        body = json.dumps(
                            translate_tool_text_response(
                                json.loads(body),
                                allowed_tool_names,
                                reject_shell_writes=self.server.reject_shell_writes,
                                force_patch_first=force_patch_first,
                            )
                        ).encode("utf-8")
                    except json.JSONDecodeError:
                        pass
                if stream_response and "application/json" in content_type:
                    try:
                        body = responses_sse(json.loads(body))
                        content_type = "text/event-stream"
                    except json.JSONDecodeError:
                        pass
                self.send_bytes(resp.status, body, content_type)
        except HTTPError as err:
            body = err.read()
            self.log_message("backend HTTP %d: %s", err.code, body[:1200].decode("utf-8", "replace"))
            self.send_bytes(err.code, body, err.headers.get("content-type", "application/json"))
        except URLError as err:
            self.send_json(502, {"error": {"message": str(err), "type": "proxy_error"}})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11435)
    parser.add_argument("--backend", default="http://127.0.0.1:11434")
    parser.add_argument("--model", required=True)
    parser.add_argument("--context-window", type=int, default=32768)
    parser.add_argument("--max-output-tokens", type=int, default=int(os.environ.get("LLAMA_CODEX_MAX_OUTPUT_TOKENS", "2048")))
    parser.add_argument("--deny-tool-pattern", default=os.environ.get("LLAMA_CODEX_DENY_TOOL_PATTERN", ""))
    parser.add_argument(
        "--reject-shell-writes",
        action="store_true",
        default=os.environ.get("LLAMA_CODEX_REJECT_SHELL_WRITES", "").lower() in {"1", "true", "yes"},
    )
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Proxy)
    server.backend = args.backend
    server.model = args.model
    server.context_window = args.context_window
    server.max_output_tokens = args.max_output_tokens
    server.deny_tool_pattern = args.deny_tool_pattern
    server.reject_shell_writes = args.reject_shell_writes
    print(f"ollama-codex-proxy listening on http://{args.host}:{args.port} -> {args.backend}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
