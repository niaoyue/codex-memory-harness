from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from init_storage import ensure_storage_layout


SERVER_INFO = {"name": "codex-memory", "version": "0.1.0"}


def _api():
    import memory_api

    return memory_api


def _read_message() -> dict | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        name, value = line.decode("utf-8").split(":", 1)
        headers[name.strip().lower()] = value.strip()

    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    body = sys.stdin.buffer.read(length)
    return json.loads(body.decode("utf-8")) if body else None


def _write_message(message: dict) -> None:
    encoded = json.dumps(message, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def _success(message_id: object, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id: object, code: int, text: str) -> dict:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": text}}


def _handle_request(message: dict) -> dict | None:
    method = message.get("method")
    message_id = message.get("id")

    if method == "initialize":
        return _success(
            message_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"resources": {}, "tools": {}, "prompts": {}},
                "serverInfo": SERVER_INFO,
            },
        )
    if method == "ping":
        return _success(message_id, {})
    if method == "tools/list":
        return _success(message_id, {"tools": _api().tool_specs()})
    if method == "resources/list":
        return _success(message_id, {"resources": _api().resource_specs()})
    if method == "resources/read":
        return _handle_resource_read(message_id, message)
    if method == "tools/call":
        return _handle_tool_call(message_id, message)
    if method == "prompts/list":
        return _success(message_id, {"prompts": []})
    if method == "prompts/get":
        return _error(message_id, -32601, "No prompts are defined yet.")
    if method == "shutdown":
        return _success(message_id, {})
    if message_id is None:
        return None
    return _error(message_id, -32601, f"Method not implemented: {method}")


def _handle_resource_read(message_id: object, message: dict) -> dict:
    try:
        uri = str(message["params"]["uri"])
        text, mime_type = _api().resource_payload(uri)
        return _success(
            message_id,
            {"contents": [{"uri": uri, "mimeType": mime_type, "text": text}]},
        )
    except (KeyError, ValueError) as exc:
        return _error(message_id, -32602, str(exc))


def _handle_tool_call(message_id: object, message: dict) -> dict:
    try:
        params = message.get("params", {})
        name = str(params["name"])
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be an object.")
        return _success(message_id, _api().call_tool(name, arguments))
    except (KeyError, ValueError) as exc:
        return _error(message_id, -32602, str(exc))


def _serve_stdio() -> int:
    ensure_storage_layout()
    while True:
        message = _read_message()
        if message is None:
            return 0
        if message.get("method") == "exit":
            return 0
        if message.get("method") == "notifications/initialized":
            continue
        response = _handle_request(message)
        if response is not None:
            _write_message(response)


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal MCP server stub for Codex Memory.")
    parser.add_argument("--check", action="store_true", help="Validate startup and print status.")
    parser.add_argument("--stdio", action="store_true", help="Run as an MCP stdio server.")
    parser.add_argument("--memory-scope", choices=["project", "global", "auto"], help="Memory storage scope.")
    parser.add_argument("--memory-cwd", help="Directory used to resolve project memory.")
    args = parser.parse_args()
    if args.memory_scope:
        os.environ["CODEX_MEMORY_SCOPE"] = args.memory_scope
    if args.memory_cwd:
        os.environ["CODEX_MEMORY_CWD"] = args.memory_cwd
    layout = ensure_storage_layout()

    if args.check:
        print(
            json.dumps(
                {
                    "server": SERVER_INFO,
                    "storage": layout,
                    "resources": [item["uri"] for item in _api().resource_specs()],
                    "tools": [item["name"] for item in _api().tool_specs()],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.stdio:
        return _serve_stdio()
    print("Codex Memory MCP stub is ready. Use --check or --stdio.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
