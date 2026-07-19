"""Fix DB-GPT stream_generator when openai_format=True but chunks are plain str.

Upstream assumes ModelOutput when openai_format is set, but stream_call still
yields strings when text_output=True (default). That raises:
  AttributeError: 'str' object has no attribute 'has_text'
and aborts the SSE stream after SQL generation.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def apply() -> None:
    from dbgpt_app.openapi.api_v1 import api_v1

    if getattr(api_v1.stream_generator, "_nanobase_patched", False):
        return

    original = api_v1.stream_generator

    async def stream_generator(  # type: ignore[no-untyped-def]
        chat,
        incremental: bool,
        model_name: str,
        text_output: bool = True,
        openai_format: bool = False,
        conv_uid=None,
    ):
        # OpenAI-compatible path requires ModelOutput objects.
        if openai_format:
            text_output = False
        async for chunk in original(
            chat,
            incremental,
            model_name,
            text_output=text_output,
            openai_format=openai_format,
            conv_uid=conv_uid,
        ):
            yield chunk

    stream_generator._nanobase_patched = True  # type: ignore[attr-defined]
    api_v1.stream_generator = stream_generator  # type: ignore[assignment]
    logger.info("Applied Nanobase stream_generator openai_format/text_output patch")
