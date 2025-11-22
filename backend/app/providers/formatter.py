import logging
import os
from typing import Callable

from openai import AsyncOpenAI

from ..models import JobStatus


async def stream_formatting(
    raw_text: str, job_id: str, on_progress: Callable[[dict], None]
) -> str:
    """Stream formatting via DeepSeek-compatible chat completion."""
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    api_key = os.getenv("DEEPSEEK_API_KEY")
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    system_prompt = (
        "你是一个乐于助人的助手。你的任务是纠正转录文本中的所有拼写错误。"
        "仅添加必要的标点符号，例如句号、逗号，并且仅使用提供的上下文。"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": raw_text},
    ]

    stream = await client.chat.completions.create(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        messages=messages,
        stream=True,
    )
    chunks: list[str] = []
    token_count = 0
    async for chunk in stream:
        delta = None
        if hasattr(chunk, "choices") and chunk.choices:
            delta = chunk.choices[0].delta.content
        elif isinstance(chunk, dict):
            delta = chunk.get("content")
        if delta:
            chunks.append(delta)
            token_count += len(delta.split())
            accumulated = "".join(chunks)
            on_progress(
                {
                    "stage": JobStatus.formatting,
                    "words": token_count,
                    "formatted_text": accumulated,
                    "chunk": delta,
                }
            )
    return "".join(chunks)
