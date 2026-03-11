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
        "你是一个乐于助人的转录整理助手。"
        "你的任务是纠正转录文本中的拼写错误，并补充必要的标点。"
        "如果输入中包含“分片”“时间”“重叠”等分片标识，这说明原始音频被切片转录过，"
        "相邻片段之间会有重叠内容。你必须基于上下文把这些分片自然拼接，"
        "删除因为重叠导致的重复字词、重复短句和重复段落，但不要遗漏有效内容。"
        "输出中不要保留任何分片标识、时间范围或技术性注释，只保留整理后的正文。"
        "除去纠错、补标点和消除重叠重复之外，不要凭空补充事实。"
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
