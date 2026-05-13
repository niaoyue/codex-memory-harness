#!/usr/bin/env python3
"""Render CLIProxyAPI alias snippets for image_generation workflows."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_ALIAS_PREFIX = "gpt-image"
DEFAULT_BACKGROUND = "auto"
DEFAULT_PROTOCOL = "codex"
DEFAULT_QUALITY = "high"
DEFAULT_SIZES: tuple[str, ...] = ("1024x1024",)
SIZE_PATTERN = re.compile(r"^\d+x\d+$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate CLIProxyAPI YAML snippets for image-generation aliases."
    )
    parser.add_argument(
        "--base-model",
        default="gpt-4.1",
        help="Underlying text-capable model that supports the image_generation tool.",
    )
    parser.add_argument(
        "--alias-prefix",
        default=DEFAULT_ALIAS_PREFIX,
        help="Prefix used to build alias names. Size is appended automatically.",
    )
    parser.add_argument(
        "--size",
        dest="sizes",
        action="append",
        default=[],
        help="Image size in WIDTHxHEIGHT form. Repeat to emit multiple aliases.",
    )
    parser.add_argument(
        "--quality",
        default=DEFAULT_QUALITY,
        choices=("auto", "low", "medium", "high"),
        help="Image quality injected into the tool definition.",
    )
    parser.add_argument(
        "--background",
        default=DEFAULT_BACKGROUND,
        choices=("auto", "opaque", "transparent"),
        help="Background mode injected into the tool definition.",
    )
    parser.add_argument(
        "--protocol",
        default=DEFAULT_PROTOCOL,
        help="CLIProxyAPI protocol label for the alias model entry.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional file path. Writes UTF-8 text without BOM when set.",
    )
    return parser.parse_args()


def normalize_sizes(raw_sizes: Sequence[str]) -> tuple[str, ...]:
    if not raw_sizes:
        return DEFAULT_SIZES

    normalized: list[str] = []
    for size in raw_sizes:
        if not SIZE_PATTERN.fullmatch(size):
            raise SystemExit(f"Invalid size: {size}. Expected WIDTHxHEIGHT.")
        if size not in normalized:
            normalized.append(size)
    return tuple(normalized)


def build_tool_json(size: str, quality: str, background: str) -> str:
    tool = {
        "type": "image_generation",
        "size": size,
        "quality": quality,
        "background": background,
    }
    return json.dumps([tool], ensure_ascii=False, separators=(",", ":"))


def render_alias_lines(
    base_model: str,
    alias_prefix: str,
    sizes: Iterable[str],
    protocol: str,
    quality: str,
    background: str,
) -> list[str]:
    lines = ["oauth-model-alias:", "  codex:"]

    aliases = []
    for size in sizes:
        alias_name = f"{alias_prefix}-{size}"
        aliases.append((alias_name, size))
        lines.extend(
            [
                f"    - name: {base_model}",
                f"      alias: {alias_name}",
                "      fork: true",
            ]
        )

    lines.extend(["", "payload:", "  override-raw:"])
    tool_choice = json.dumps({"type": "image_generation"}, separators=(",", ":"))

    for alias_name, size in aliases:
        tools_json = build_tool_json(size=size, quality=quality, background=background)
        lines.extend(
            [
                "    - models:",
                f"        - name: {alias_name}",
                f"          protocol: {protocol}",
                "      params:",
                f"        tools: '{tools_json}'",
                f"        tool_choice: '{tool_choice}'",
            ]
        )

    return lines


def main() -> None:
    args = parse_args()
    sizes = normalize_sizes(args.sizes)
    rendered = "\n".join(
        render_alias_lines(
            base_model=args.base_model,
            alias_prefix=args.alias_prefix,
            sizes=sizes,
            protocol=args.protocol,
            quality=args.quality,
            background=args.background,
        )
    )
    output_text = f"{rendered}\n"

    if args.output:
        args.output.write_text(output_text, encoding="utf-8")
        print(f"Wrote alias snippet to {args.output}")
        return

    print(output_text, end="")


if __name__ == "__main__":
    main()
