from __future__ import annotations

import os
from collections.abc import Mapping


REVIEW_GATE_RUNNING_ENV = "CODEX_REVIEW_GATE_RUNNING"
XHIGH_REVIEW_DISPATCH_DISABLE_ENV = "CODEX_XHIGH_REVIEW_DISPATCH_DISABLE"
TRUE_ENV_VALUES = {"1", "true", "yes", "on"}


def env_flag(name: str, environ: Mapping[str, str] | None = None) -> bool:
    value = (environ or os.environ).get(name, "")
    return str(value).strip().lower() in TRUE_ENV_VALUES


def review_gate_running(environ: Mapping[str, str] | None = None) -> bool:
    return env_flag(REVIEW_GATE_RUNNING_ENV, environ)


def xhigh_review_dispatch_disabled(environ: Mapping[str, str] | None = None) -> bool:
    return review_gate_running(environ) or env_flag(XHIGH_REVIEW_DISPATCH_DISABLE_ENV, environ)


def review_gate_child_env(base_env: Mapping[str, str] | None = None) -> dict[str, str]:
    child_env = dict(base_env or os.environ)
    child_env[REVIEW_GATE_RUNNING_ENV] = "1"
    child_env[XHIGH_REVIEW_DISPATCH_DISABLE_ENV] = "1"
    return child_env
