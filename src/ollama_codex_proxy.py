#!/usr/bin/env python3
import argparse
import html
import json
import os
import re
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


def translate_tool_text_response(data, allowed_names):
    data = normalize_response_text(data)
    output = data.get("output")
    if not isinstance(output, list):
        return data
    for index, item in enumerate(output):
        if item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        text = "".join(part.get("text", "") for part in content if part.get("type") == "output_text")
        parsed = parse_tool_text(text, allowed_names)
        if not parsed:
            continue
        name, arguments = parsed
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
                            "deny_tool_pattern": self.server.deny_tool_pattern,
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
            stream_response = bool(payload.get("stream"))
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
            self.forward(payload, allowed_tool_names=allowed_tool_names, stream_response=stream_response)
            return
        self.forward(read_json(self))

    def forward(self, payload=None, allowed_tool_names=None, stream_response=False):
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
                        body = json.dumps(translate_tool_text_response(json.loads(body), allowed_tool_names)).encode("utf-8")
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
    parser.add_argument("--deny-tool-pattern", default=os.environ.get("LLAMA_CODEX_DENY_TOOL_PATTERN", ""))
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Proxy)
    server.backend = args.backend
    server.model = args.model
    server.context_window = args.context_window
    server.deny_tool_pattern = args.deny_tool_pattern
    print(f"ollama-codex-proxy listening on http://{args.host}:{args.port} -> {args.backend}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
