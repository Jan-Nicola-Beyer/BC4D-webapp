"""Unified Claude API client — ALL API calls go through here.

Never import anthropic directly in other modules.
Handles: model routing, retry with backoff, cost tracking.
"""

from __future__ import annotations
import logging, time
from typing import Optional

from bc4d_intel import constants as C

log = logging.getLogger("bc4d_intel.ai")


def call_claude(
    system: str,
    user_msg: str,
    task: str = "tagging",  # "tagging" | "report"
    api_key: str = "",
    max_tokens: int = 1000,
    stream_cb=None,
) -> str:
    """Call Claude API with task-based model routing.

    Args:
        task: "tagging" → Haiku (cheap, bulk), "report" → Sonnet (quality)
        api_key: Anthropic API key
        stream_cb: Optional callback for streaming tokens
    """
    import anthropic, httpx

    model = C.AI_MODELS.get(task, C.AI_MODELS["tagging"])
    client = anthropic.Anthropic(
        api_key=api_key,
        timeout=httpx.Timeout(120.0, connect=10.0),
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            if stream_cb:
                full_text = []
                with client.messages.stream(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user_msg}],
                ) as stream:
                    for text in stream.text_stream:
                        full_text.append(text)
                        stream_cb(text)
                return "".join(full_text)
            else:
                resp = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user_msg}],
                )
                return resp.content[0].text

        except anthropic.APIStatusError as e:
            if "overloaded" in str(e).lower() and attempt < max_retries - 1:
                wait = 10 * (attempt + 1)
                log.warning("API overloaded, retrying in %ds (%d/%d)",
                            wait, attempt + 1, max_retries)
                if stream_cb:
                    stream_cb(f"\n*API overloaded, retrying in {wait}s...*\n")
                time.sleep(wait)
            else:
                raise
