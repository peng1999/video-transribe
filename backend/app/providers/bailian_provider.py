import asyncio
import logging
import os
from pathlib import Path
from typing import Callable, Optional

import httpx

from ..models import JobStatus
from .oss_storage import upload_audio_and_sign_url, OSSConfigError


DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/api/v1"
FILETRANS_MODEL = "qwen3-asr-flash-filetrans"


class BailianConfigError(RuntimeError):
    pass


def _get_api_key() -> str:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise BailianConfigError("DASHSCOPE_API_KEY is required for Bailian provider")
    return api_key


async def _submit_task(client: httpx.AsyncClient, file_url: str) -> str:
    headers = {
        "Authorization": f"Bearer {_get_api_key()}",
        "X-DashScope-Async": "enable",
    }
    payload = {
        "model": FILETRANS_MODEL,
        "input": {"file_url": file_url},
        "parameters": {"language": "zh", "enable_itn": True},
    }
    resp = await client.post(
        f"{DASHSCOPE_BASE}/services/audio/asr/transcription",
        json=payload,
        headers=headers,
    )
    resp.raise_for_status()
    data = resp.json()
    output = data.get("output", data)
    task_id = output.get("task_id")
    if not task_id:
        raise RuntimeError(f"missing task_id in bailian response: {output}")
    return task_id


async def _fetch_task(client: httpx.AsyncClient, task_id: str) -> dict:
    headers = {"Authorization": f"Bearer {_get_api_key()}"}
    resp = await client.post(f"{DASHSCOPE_BASE}/tasks/{task_id}", headers=headers)
    resp.raise_for_status()
    return resp.json()


def _extract_result_url(task_payload: dict) -> Optional[str]:
    output = task_payload.get("output", task_payload)
    results = output.get("results") or []
    if not results:
        return None
    first = results[0]
    return first.get("transcription_url") or first.get("url")


async def _download_transcription(client: httpx.AsyncClient, url: str) -> str:
    resp = await client.get(url)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type:
        data = resp.json()
        for key in ("transcription", "text", "result"):
            if key in data:
                return data[key]
    return resp.text


async def transcribe(
    audio_path: Path,
    job_id: str,
    on_progress: Callable[[dict], None],
    on_task_id: Callable[[str], None],
) -> str:
    """Submit async ASR to Bailian and poll until completion."""
    try:
        file_url = upload_audio_and_sign_url(audio_path, job_id)
    except OSSConfigError as exc:
        raise BailianConfigError(str(exc)) from exc

    on_progress(
        {
            "stage": JobStatus.transcribing,
            "message": "已上传 OSS，提交百炼任务",
        }
    )
    async with httpx.AsyncClient(timeout=60) as client:
        task_id = await _submit_task(client, file_url)
        on_task_id(task_id)
        on_progress(
            {
                "stage": JobStatus.transcribing,
                "message": f"百炼任务已提交，task_id={task_id}",
            }
        )
        while True:
            await asyncio.sleep(2)
            task_payload = await _fetch_task(client, task_id)
            output = task_payload.get("output", task_payload)
            status = output.get("task_status")
            if status in {"RUNNING", "PENDING"}:
                on_progress(
                    {
                        "stage": JobStatus.transcribing,
                        "message": f"百炼处理中（{status}）",
                    }
                )
                continue
            if status == "FAILED":
                error_msg = output.get("message") or "Bailian task failed"
                raise RuntimeError(error_msg)
            if status == "SUCCEEDED":
                url = _extract_result_url(task_payload)
                if not url:
                    raise RuntimeError("transcription_url 缺失")
                text = await _download_transcription(client, url)
                on_progress(
                    {
                        "stage": JobStatus.transcribing,
                        "raw_text": text,
                        "words": len(text.split()),
                        "message": "百炼转录完成",
                    }
                )
                return text
            raise RuntimeError(f"Unknown bailian status: {status}")
