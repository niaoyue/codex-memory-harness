#!/usr/bin/env python3
"""Generate an image via a Responses API compatible endpoint and save it locally."""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BACKGROUND = "auto"
DEFAULT_MODEL = "gpt-4.1"
DEFAULT_OUTPUT = Path("generated.png")
DEFAULT_QUALITY = "high"
DEFAULT_SIZE = "1024x1024"
DEFAULT_TIMEOUT_SECONDS = 300
RETRY_DELAY_RATE_LIMIT_SECONDS = 20
RETRY_DELAY_TRANSIENT_SECONDS = 2
RETRY_LIMIT = 1
TRANSIENT_STATUS_CODES = {500, 502, 503, 504}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Call a Responses API compatible endpoint with the image_generation tool."
    )
    parser.add_argument("prompt", help="Prompt used to generate the image.")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Text-capable model used with the image_generation tool.",
    )
    parser.add_argument(
        "--size",
        default=DEFAULT_SIZE,
        help="Requested image size, for example 1024x1024.",
    )
    parser.add_argument(
        "--quality",
        default=DEFAULT_QUALITY,
        choices=("auto", "low", "medium", "high"),
        help="Requested image quality.",
    )
    parser.add_argument(
        "--background",
        default=DEFAULT_BACKGROUND,
        choices=("auto", "opaque", "transparent"),
        help="Requested image background mode.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output file path for the generated image.",
    )
    parser.add_argument(
        "--endpoint",
        help="Full responses endpoint URL. Overrides OPENAI_RESPONSES_URL and OPENAI_BASE_URL.",
    )
    parser.add_argument(
        "--api-key-env",
        default="OPENAI_API_KEY",
        help="Environment variable that stores the API key.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="HTTP timeout in seconds.",
    )
    return parser.parse_args()


def resolve_api_key(env_name: str) -> str:
    api_key = os.getenv(env_name)
    if not api_key:
        raise SystemExit(f"Missing API key environment variable: {env_name}")
    return api_key


def resolve_endpoint(explicit_endpoint: str | None) -> str:
    if explicit_endpoint:
        return explicit_endpoint.rstrip("/")

    responses_url = os.getenv("OPENAI_RESPONSES_URL")
    if responses_url:
        return responses_url.rstrip("/")

    base_url = os.getenv("OPENAI_BASE_URL")
    if not base_url:
        raise SystemExit(
            "Missing endpoint. Set --endpoint, OPENAI_RESPONSES_URL, or OPENAI_BASE_URL."
        )

    normalized = base_url.rstrip("/")
    if normalized.endswith("/responses"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/responses"
    return f"{normalized}/v1/responses"


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "model": args.model,
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": args.prompt}],
            }
        ],
        "tool_choice": {"type": "image_generation"},
        "tools": [
            {
                "type": "image_generation",
                "size": args.size,
                "quality": args.quality,
                "background": args.background,
            }
        ],
        "stream": False,
        "store": False,
    }


def should_retry(status_code: int | None, attempt: int) -> tuple[bool, int]:
    if attempt >= RETRY_LIMIT:
        return False, 0
    if status_code == 429:
        return True, RETRY_DELAY_RATE_LIMIT_SECONDS
    if status_code in TRANSIENT_STATUS_CODES:
        return True, RETRY_DELAY_TRANSIENT_SECONDS
    return False, 0


def post_json(
    endpoint: str,
    payload: dict[str, Any],
    api_key: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    request_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    for attempt in range(RETRY_LIMIT + 1):
        request = urllib.request.Request(
            endpoint,
            data=request_body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
                return json.loads(response_body)
        except urllib.error.HTTPError as error:
            response_text = error.read().decode("utf-8", errors="replace")
            retry, delay_seconds = should_retry(error.code, attempt)
            if retry:
                time.sleep(delay_seconds)
                continue
            raise SystemExit(f"Request failed with HTTP {error.code}: {response_text}") from error
        except (urllib.error.URLError, TimeoutError, socket.timeout) as error:
            retry, delay_seconds = should_retry(500, attempt)
            if retry:
                time.sleep(delay_seconds)
                continue
            raise SystemExit(
                f"Request failed due to network or timeout error: {error}"
            ) from error

    raise SystemExit("Request failed after retries.")


def extract_image_result(response_json: dict[str, Any]) -> tuple[str, str | None]:
    output_items = response_json.get("output", [])
    for item in output_items:
        if item.get("type") != "image_generation_call":
            continue
        result = item.get("result")
        if isinstance(result, str) and result:
            return result, item.get("revised_prompt")

    raise SystemExit(
        "No image_generation_call result found in response. "
        "The endpoint may have ignored the tool settings."
    )


def write_image(output_path: Path, image_base64: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image_bytes = base64.b64decode(image_base64)
    output_path.write_bytes(image_bytes)


def main() -> None:
    args = parse_args()
    api_key = resolve_api_key(args.api_key_env)
    endpoint = resolve_endpoint(args.endpoint)
    payload = build_payload(args)
    response_json = post_json(
        endpoint=endpoint,
        payload=payload,
        api_key=api_key,
        timeout_seconds=args.timeout_seconds,
    )
    image_base64, revised_prompt = extract_image_result(response_json)
    write_image(args.output, image_base64)

    print(f"Saved image to {args.output}")
    if revised_prompt:
        print(f"Revised prompt: {revised_prompt}")


if __name__ == "__main__":
    main()
