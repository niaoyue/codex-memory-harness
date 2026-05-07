from __future__ import annotations

import os

from install_support import select_mcp_python_runtime


def npm_argv(*args: str) -> list[str]:
    return ["npm.cmd" if os.name == "nt" else "npm", *args]


def mvn_argv(*args: str) -> list[str]:
    return ["mvn.cmd" if os.name == "nt" else "mvn", *args]


def python_argv(script: str) -> list[str]:
    runtime = select_mcp_python_runtime()
    return [str(runtime["command"]), *[str(arg) for arg in runtime.get("prefix_args", [])], "-X", "utf8", "-c", script]
