from __future__ import annotations

import json
import os
import sys
from typing import Any


TRUE_VALUES = {"1", "true", "yes", "on", "debug"}


def debug_log(event: str, payload: dict[str, Any]) -> None:
    enabled = os.environ.get("CODEX_MEMORY_INSTALL_DEBUG", "").strip().lower()
    if enabled not in TRUE_VALUES:
        return
    safe_payload = {"event": event, **payload}
    sys.stderr.write(
        "[codex-memory-install][DEBUG] "
        + json.dumps(safe_payload, ensure_ascii=False, sort_keys=True)
        + "\n"
    )
