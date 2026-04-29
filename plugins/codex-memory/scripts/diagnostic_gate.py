from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

CODE_EXTENSIONS = {".cs", ".ts", ".tsx", ".js", ".jsx", ".lua"}
SKIP_DIRS = {"node_modules", "Library", "Temp", "Logs", "dist", "build", "__pycache__", ".git", ".codex"}
SKIP_DIRS_NORMALIZED = {item.lower() for item in SKIP_DIRS}
MAX_FILES = 500
MAX_BYTES = 250_000
ENABLED_PATTERNS = (
    re.compile(r"(?i)\b(ai[_\-.]?diagnostics?|diagnostic_logging)\.enabled\s*[:=]\s*true\b"),
    re.compile(r"(?i)\b(ai[_-]?diagnostics?[_-]?enabled|enable_ai_diagnostics)\s*[:=]\s*(true|1)\b"),
    re.compile(r"(?i)\b(ai[_\-.]?diagnostics?|aiDiagnostics|diagnostic_logging)\s*[:=]\s*\{[^}\n]*\benabled\s*:\s*true\b"),
    re.compile(r"(?i)#define\s+(ENABLE_AI_DIAGNOSTICS|AI_DIAGNOSTICS_ENABLED)\b"),
)
DIAGNOSTIC_OBJECT_START = re.compile(r"(?i)\b(ai[_\-.]?diagnostics?|aiDiagnostics|diagnostic_logging)\s*[:=]\s*\{")
OBJECT_ENABLED_FIELD = re.compile(r"(?i)(?:\benabled\b|['\"]enabled['\"])\s*:\s*true\b")
OBJECT_SINK_FIELD = re.compile(r"(?i)(?:\bsink\b|['\"]sink['\"])\s*:\s*['\"]?(http|file|console)")
SINK_PATTERNS = (
    re.compile(r"(?i)\b(ai[_\-.]?diagnostics?|diagnostic_logging)\.sink\s*[:=]\s*['\"]?(http|file|console)"),
    re.compile(r"(?i)\b(ai[_\-.]?diagnostics?|aiDiagnostics|diagnostic_logging)\s*[:=]\s*\{[^}\n]*\bsink\s*:\s*['\"]?(http|file|console)"),
)
LOG_PATTERNS = (
    re.compile(r"\bDebug\.(?:LogWarningFormat|LogErrorFormat|LogFormat|LogException|LogWarning|LogError|Log)\s*\("),
    re.compile(r"\bconsole\.(?:log|warn|error)\s*\("),
    re.compile(r"\bcc\.log\s*\("),
    re.compile(r"(?<!\.)\bprint\s*\("),
)
FACADE_HINTS = ("DiagnosticLog", "AiDiagnosticLogger", "ProjectLogger.Diagnostics")
FACADE_FILE_STEMS = {"diagnosticlog", "aidiagnosticlogger"}


def evaluate_release_gate(project_root: Path, route_plan: dict[str, Any]) -> dict[str, Any]:
    release_required = route_plan.get("risk_level") == "release_blocking"
    if not release_required:
        return gate("skipped", False, "Release diagnostic gate not required.", [], 0)
    root = project_root.resolve()
    files, truncated, oversized = collect_files(root, route_plan)
    findings = scan_files(root, files)
    status = "failed" if findings else "manual_required" if truncated or oversized or not files else "passed"
    summary = (
        f"Found {len(findings)} diagnostic release issue(s) in {len(files)} scanned file(s)."
        if findings
        else f"Skipped {oversized} oversized supported file(s); manual review is required."
        if oversized
        else f"Diagnostic release scan reached the {MAX_FILES} file limit; manual review is required."
        if truncated
        else "Diagnostic release scan covered no supported files; manual review is required."
        if not files
        else f"No AI diagnostic release issues found in {len(files)} scanned file(s)."
    )
    return gate(status, True, summary, findings, len(files), truncated)


def gate(
    status: str,
    blocking: bool,
    summary: str,
    findings: list[dict[str, Any]],
    scanned: int,
    truncated: bool = False,
) -> dict[str, Any]:
    return {
        "status": status,
        "blocking": blocking,
        "summary": summary,
        "scanned_files": scanned,
        "truncated": truncated,
        "findings": findings[:50],
    }


def collect_files(project_root: Path, route_plan: dict[str, Any]) -> tuple[list[Path], bool, int]:
    files: list[Path] = []
    seen: set[str] = set()
    truncated = False
    oversized = 0
    scopes = route_scopes(route_plan)
    for scope in scopes or ["."]:
        if len(files) >= MAX_FILES:
            truncated = True
            break
        candidate = safe_path(project_root, scope)
        if candidate is None or not candidate.exists():
            continue
        if candidate.is_file():
            if include_file(project_root, candidate):
                append_file(files, seen, candidate)
            elif is_oversized_supported_file(project_root, candidate):
                oversized += 1
        elif candidate.is_dir():
            for path, too_large in iter_code_file_candidates(project_root, candidate):
                if too_large:
                    oversized += 1
                    continue
                if len(files) >= MAX_FILES:
                    truncated = True
                    break
                append_file(files, seen, path)
        if truncated:
            break
    return sorted(files, key=lambda path: path.as_posix())[:MAX_FILES], truncated, oversized


def append_file(files: list[Path], seen: set[str], path: Path) -> None:
    key = path.as_posix().lower()
    if key not in seen:
        seen.add(key)
        files.append(path)


def iter_code_file_candidates(root: Path, directory: Path):
    pending = [directory]
    while pending:
        current = pending.pop()
        if is_skipped_path(root, current):
            continue
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if not is_skipped_path(root, entry):
                    pending.append(entry)
            elif is_supported_file(root, entry):
                yield entry, is_oversized_supported_file(root, entry)


def route_scopes(route_plan: dict[str, Any]) -> list[str]:
    scopes: list[str] = []
    for route in route_plan.get("routes") if isinstance(route_plan.get("routes"), list) else []:
        if not isinstance(route, dict):
            continue
        scopes.extend(string_list(route.get("assigned_scope")))
        scopes.extend(string_list(route.get("cwd")))
    for target in route_plan.get("verification_plan") if isinstance(route_plan.get("verification_plan"), list) else []:
        if isinstance(target, dict):
            scopes.extend(string_list(target.get("cwd")))
    return [scope for scope in unique_text(scopes) if scope]


def safe_path(root: Path, value: str) -> Path | None:
    candidate = (root / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def include_file(root: Path, path: Path) -> bool:
    if not is_supported_file(root, path):
        return False
    try:
        return path.stat().st_size <= MAX_BYTES
    except OSError:
        return False


def is_supported_file(root: Path, path: Path) -> bool:
    return path.is_file() and path.suffix in CODE_EXTENSIONS and not is_skipped_path(root, path)


def is_oversized_supported_file(root: Path, path: Path) -> bool:
    if not is_supported_file(root, path):
        return False
    try:
        return path.stat().st_size > MAX_BYTES
    except OSError:
        return False


def is_skipped_path(root: Path, path: Path) -> bool:
    try:
        parts = path.resolve().relative_to(root).parts
    except ValueError:
        return True
    return any(part.lower() in SKIP_DIRS_NORMALIZED for part in parts)


def scan_files(root: Path, files: list[Path]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        in_block_comment = False
        in_lua_block_comment = False
        in_string_delimiter = ""
        in_template_string = False
        diagnostic_object_depth = 0
        for lineno, line in enumerate(lines, 1):
            code, in_block_comment, in_lua_block_comment, in_string_delimiter, in_template_string = code_for_scan(
                line,
                in_block_comment,
                in_lua_block_comment,
                in_string_delimiter,
                in_template_string,
                path.suffix,
            )
            findings.extend(line_findings(root, path, lineno, code, diagnostic_object_depth > 0))
            diagnostic_object_depth = update_diagnostic_object_depth(code, diagnostic_object_depth)
    return findings


def line_findings(root: Path, path: Path, lineno: int, line: str, diagnostic_object: bool = False) -> list[dict[str, Any]]:
    text = line.strip()
    if not text or text.startswith("//") or text.startswith("# "):
        return []
    result: list[dict[str, Any]] = []
    for pattern in ENABLED_PATTERNS:
        if pattern.search(text):
            result.append(finding(root, path, lineno, "diagnostic_enabled", "AI diagnostic flag is enabled."))
    for pattern in SINK_PATTERNS:
        if pattern.search(text):
            result.append(finding(root, path, lineno, "diagnostic_sink", "AI diagnostic sink is still configured."))
    if diagnostic_object and OBJECT_ENABLED_FIELD.search(text):
        result.append(finding(root, path, lineno, "diagnostic_enabled", "AI diagnostic flag is enabled."))
    if diagnostic_object and OBJECT_SINK_FIELD.search(text):
        result.append(finding(root, path, lineno, "diagnostic_sink", "AI diagnostic sink is still configured."))
    if not is_facade_file(path):
        log_text = without_facade_invocations(text)
        for pattern in LOG_PATTERNS:
            if pattern.search(log_text):
                result.append(finding(root, path, lineno, "bare_log", "Bare runtime log bypasses diagnostic facade."))
    return result


def update_diagnostic_object_depth(text: str, current_depth: int) -> int:
    start = DIAGNOSTIC_OBJECT_START.search(text)
    if start:
        current_depth += text[start.start():].count("{") - text[start.start():].count("}")
    elif current_depth:
        current_depth += text.count("{") - text.count("}")
    return max(current_depth, 0)


def code_for_scan(
    line: str,
    in_block_comment: bool,
    in_lua_block_comment: bool,
    in_string_delimiter: str,
    in_template_string: bool,
    suffix: str,
) -> tuple[str, bool, bool, str, bool]:
    result: list[str] = []
    index = 0
    quote = "`" if in_template_string else in_string_delimiter
    while index < len(line):
        char = line[index]
        next_char = line[index + 1] if index + 1 < len(line) else ""
        if in_lua_block_comment:
            end = line.find("]]", index)
            if end == -1:
                index = len(line)
            else:
                in_lua_block_comment = False
                index = end + 2
            continue
        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                index += 2
            else:
                index += 1
            continue
        if quote:
            if quote == '"""':
                end = line.find('"""', index)
                if end == -1:
                    index = len(line)
                else:
                    quote = ""
                    index = end + 3
            elif quote == "`" and char == "\\":
                index += 2
            elif quote == "`" and char == "$" and next_char == "{":
                expression, index = consume_template_expression(line, index + 2)
                cleaned, _, _, _, _ = code_for_scan(expression, False, False, "", False, suffix)
                result.append(cleaned)
            elif quote == "`" and char == quote:
                quote = ""
                index += 1
            elif quote != "`" and char == "\\":
                index += 2
            elif quote == '"' and char == '"' and next_char == '"':
                index += 2
            elif char == quote:
                quote = ""
                index += 1
            else:
                index += 1
            continue
        if char == "/" and next_char == "*":
            in_block_comment = True
            index += 2
            continue
        if char == "/" and next_char == "/":
            break
        if suffix == ".lua" and char == "-" and next_char == "-":
            if line[index + 2:index + 4] == "[[":
                end = line.find("]]", index + 4)
                if end == -1:
                    in_lua_block_comment = True
                    break
                index = end + 2
                continue
            break
        if line[index:index + 3] == '"""':
            end = line.find('"""', index + 3)
            if end == -1:
                quote = '"""'
                index = len(line)
            else:
                index = end + 3
            continue
        if char == "`":
            quote = "`"
            index += 1
            continue
        if char in {"'", '"'}:
            content, index, closed = consume_string(line, index, verbatim=index > 0 and line[index - 1] == "@")
            result.append(string_placeholder(content))
            if not closed:
                quote = char
            continue
        result.append(char)
        index += 1
    return "".join(result), in_block_comment, in_lua_block_comment, "" if quote == "`" else quote, quote == "`"


def consume_string(line: str, start: int, verbatim: bool = False) -> tuple[str, int, bool]:
    quote = line[start]
    index = start + 1
    content: list[str] = []
    while index < len(line):
        char = line[index]
        if verbatim and char == quote and index + 1 < len(line) and line[index + 1] == quote:
            index += 2
            continue
        if not verbatim and char == "\\":
            index += 2
            continue
        if char == quote:
            return "".join(content), index + 1, True
        content.append(char)
        index += 1
    return "".join(content), len(line), False


def consume_template_expression(line: str, start: int) -> tuple[str, int]:
    index = start
    depth = 1
    quote = ""
    result: list[str] = []
    while index < len(line):
        char = line[index]
        if quote:
            result.append(char)
            if char == "\\":
                if index + 1 < len(line):
                    result.append(line[index + 1])
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
            result.append(char)
        elif char == "{":
            depth += 1
            result.append(char)
        elif char == "}":
            depth -= 1
            if depth == 0:
                return "".join(result), index + 1
            result.append(char)
        else:
            result.append(char)
        index += 1
    return "".join(result), len(line)


def string_placeholder(content: str) -> str:
    lowered = content.strip().lower()
    if lowered in {"enabled", "sink"}:
        return f'"{lowered}"'
    for marker in ("http", "file", "console"):
        if lowered.startswith(marker):
            return f'"{marker}"'
    return '""'


def is_facade_file(path: Path) -> bool:
    return path.stem.lower() in FACADE_FILE_STEMS


def without_facade_invocations(text: str) -> str:
    for hint in FACADE_HINTS:
        prefix = rf"(?<![\w.]){re.escape(hint)}\."
        text = re.sub(prefix + r"Debug\.Log", f"{hint}.FacadeLog", text)
        text = re.sub(prefix + r"Debug\.LogWarning", f"{hint}.FacadeLogWarning", text)
        text = re.sub(prefix + r"Debug\.LogError", f"{hint}.FacadeLogError", text)
        text = re.sub(prefix + r"console\.log", f"{hint}.FacadeConsoleLog", text)
        text = re.sub(prefix + r"console\.warn", f"{hint}.FacadeConsoleWarn", text)
        text = re.sub(prefix + r"console\.error", f"{hint}.FacadeConsoleError", text)
        text = re.sub(prefix + r"cc\.log", f"{hint}.FacadeCcLog", text)
        text = re.sub(prefix + r"print", f"{hint}.FacadePrint", text)
    return text


def finding(root: Path, path: Path, lineno: int, kind: str, reason: str) -> dict[str, Any]:
    try:
        display_path = path.resolve().relative_to(root).as_posix()
    except ValueError:
        display_path = path.name
    return {"path": display_path, "line": lineno, "type": kind, "reason": reason}


def unique_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check AI diagnostic logging release gates.")
    parser.add_argument("--project-root", default=os.environ.get("CODEX_MEMORY_CWD") or os.getcwd())
    parser.add_argument("--route-file", required=True)
    args = parser.parse_args()
    route_plan = json.loads(Path(args.route_file).read_text(encoding="utf-8"))
    if isinstance(route_plan, dict) and isinstance(route_plan.get("route_plan"), dict):
        route_plan = route_plan["route_plan"]
    result = evaluate_release_gate(Path(args.project_root), route_plan)
    print(json.dumps({"ok": result["status"] in {"passed", "skipped"}, "gate": result}, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"passed", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
