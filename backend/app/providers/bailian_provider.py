import asyncio
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

import httpx

from ..models import JobStatus
from .oss_storage import upload_audio_and_sign_url, OSSConfigError


DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/api/v1"
FILETRANS_MODEL = "qwen3-asr-flash-filetrans"
FUN_ASR_MODEL = "fun-asr"
DEFAULT_BAILIAN_MODEL = FILETRANS_MODEL
DEFAULT_CHUNK_SECONDS = int(os.getenv("BAILIAN_CHUNK_SECONDS", "300"))
DEFAULT_CHUNK_OVERLAP_SECONDS = int(os.getenv("BAILIAN_CHUNK_OVERLAP_SECONDS", "15"))


class BailianConfigError(RuntimeError):
    pass


def _get_api_key() -> str:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise BailianConfigError("DASHSCOPE_API_KEY is required for Bailian provider")
    return api_key


async def _submit_task(
    client: httpx.AsyncClient, file_url: str, model: str = DEFAULT_BAILIAN_MODEL
) -> str:
    headers = {
        "Authorization": f"Bearer {_get_api_key()}",
        "X-DashScope-Async": "enable",
    }
    if model == FUN_ASR_MODEL:
        payload = {
            "model": FUN_ASR_MODEL,
            "input": {"file_urls": [file_url]},
        }
    else:
        payload = {
            "model": model,
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
    results = output.get("results")
    if isinstance(results, list):
        for item in results:
            if item.get("subtask_status") == "SUCCEEDED" and item.get(
                "transcription_url"
            ):
                return item["transcription_url"]
        for item in results:
            if item.get("transcription_url"):
                return item["transcription_url"]

    # Backward-compatible fallback for any older payload shape.
    result = task_payload.get("result")
    if isinstance(result, dict):
        return result.get("transcription_url")
    return None


def _extract_transcription_text(data: dict) -> str | None:
    for key in ("transcription", "text", "result", "transcript"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value

    transcripts = data.get("transcripts")
    if isinstance(transcripts, list):
        parts: list[str] = []
        for item in transcripts:
            if not isinstance(item, dict):
                continue
            text = item.get("text") or item.get("transcript")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        if parts:
            return "\n".join(parts)

    return None


async def _download_transcription(client: httpx.AsyncClient, url: str) -> str:
    resp = await client.get(url)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type:
        data = resp.json()
        extracted = _extract_transcription_text(data)
        if extracted:
            return extracted
    return resp.text


def _format_seconds(value: float) -> str:
    total = max(0, int(round(value)))
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _probe_duration(audio_path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout or "{}")
    duration = payload.get("format", {}).get("duration")
    if duration is None:
        raise RuntimeError(f"failed to probe duration for {audio_path}")
    return float(duration)


def _split_audio(audio_path: Path, workdir: Path) -> list[tuple[Path, float, float]]:
    duration = _probe_duration(audio_path)
    chunk_seconds = max(1, DEFAULT_CHUNK_SECONDS)
    overlap_seconds = max(0, min(DEFAULT_CHUNK_OVERLAP_SECONDS, chunk_seconds - 1))
    if duration <= chunk_seconds:
        return [(audio_path, 0.0, duration)]

    segments: list[tuple[Path, float, float]] = []
    start = 0.0
    index = 1
    while start < duration:
        end = min(duration, start + chunk_seconds)
        output = workdir / f"{audio_path.stem}-part-{index:03d}{audio_path.suffix}"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{start:.3f}",
                "-t",
                f"{end - start:.3f}",
                "-i",
                str(audio_path),
                "-vn",
                "-acodec",
                "copy",
                str(output),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        segments.append((output, start, end))
        if end >= duration:
            break
        start = max(0.0, end - overlap_seconds)
        index += 1

    return segments


async def _transcribe_single_file(
    audio_path: Path,
    job_id: str,
    on_progress: Callable[[dict], None],
    on_task_id: Callable[[str], None],
    model: str,
    chunk_label: str | None = None,
) -> str:
    try:
        file_url = await asyncio.to_thread(upload_audio_and_sign_url, audio_path, job_id)
    except OSSConfigError as exc:
        raise BailianConfigError(str(exc)) from exc

    prefix = f"{chunk_label}：" if chunk_label else ""
    on_progress(
        {
            "stage": JobStatus.transcribing,
            "message": f"{prefix}已上传 OSS，提交百炼任务",
        }
    )
    async with httpx.AsyncClient(timeout=60) as client:
        task_id = await _submit_task(client, file_url, model)
        logging.info(
            "job %s submitted bailian task %s using model %s chunk=%s",
            job_id,
            task_id,
            model,
            chunk_label,
        )
        on_task_id(task_id)
        on_progress(
            {
                "stage": JobStatus.transcribing,
                "message": f"{prefix}百炼任务已提交（{model}），task_id={task_id}",
            }
        )
        while True:
            await asyncio.sleep(2)
            task_payload = await _fetch_task(client, task_id)
            output = task_payload.get("output", task_payload)
            status = output.get("task_status")
            logging.info(
                "job %s bailian task %s status=%s chunk=%s",
                job_id,
                task_id,
                status,
                chunk_label,
            )
            if status in {"RUNNING", "PENDING"}:
                on_progress(
                    {
                        "stage": JobStatus.transcribing,
                        "message": f"{prefix}百炼处理中（{status}）",
                    }
                )
                continue
            if status == "FAILED":
                error_msg = output.get("message") or "Bailian task failed"
                raise RuntimeError(error_msg)
            if status == "SUCCEEDED":
                logging.info(
                    "job %s bailian task %s succeeded, payload=%s chunk=%s",
                    job_id,
                    task_id,
                    output,
                    chunk_label,
                )
                url = _extract_result_url(task_payload)
                if not url:
                    raise RuntimeError("transcription_url 缺失")
                return await _download_transcription(client, url)
            raise RuntimeError(f"Unknown bailian status: {status}")


async def transcribe(
    audio_path: Path,
    job_id: str,
    on_progress: Callable[[dict], None],
    on_task_id: Callable[[str], None],
    model: str = DEFAULT_BAILIAN_MODEL,
) -> str:
    """Split long audio into overlapping chunks, transcribe each, then merge."""
    with tempfile.TemporaryDirectory() as tmpdir:
        chunks = _split_audio(audio_path, Path(tmpdir))

        logging.info(
            "job %s split audio into %d chunks for Bailian model=%s",
            job_id,
            len(chunks),
            model,
        )
        if len(chunks) > 1:
            on_progress(
                {
                    "stage": JobStatus.transcribing,
                    "message": (
                        f"音频已按 {DEFAULT_CHUNK_SECONDS // 60} 分钟分片，"
                        f"相邻重叠 {DEFAULT_CHUNK_OVERLAP_SECONDS} 秒，共 {len(chunks)} 片"
                    ),
                }
            )

        merged_sections: list[str | None] = [None] * len(chunks)

        async def _transcribe_chunk(
            index: int, chunk_path: Path, start: float, end: float
        ) -> None:
            label = (
                f"第 {index}/{len(chunks)} 片 "
                f"({_format_seconds(start)}-{_format_seconds(end)})"
            )
            try:
                text = await _transcribe_single_file(
                    chunk_path,
                    f"{job_id}-chunk-{index:03d}",
                    on_progress,
                    on_task_id,
                    model,
                    chunk_label=label if len(chunks) > 1 else None,
                )
            except Exception as exc:
                raise RuntimeError(f"{label} 转录失败：{exc}") from exc

            if len(chunks) > 1:
                merged_sections[index - 1] = (
                    (
                        f"[分片 {index}/{len(chunks)} | "
                        f"时间 { _format_seconds(start)}-{_format_seconds(end)} | "
                        f"与上一片重叠 {DEFAULT_CHUNK_OVERLAP_SECONDS if index > 1 else 0} 秒]\n"
                        f"{text.strip()}"
                    )
                )
            else:
                merged_sections[index - 1] = text.strip()

            merged_text = "\n\n".join(section for section in merged_sections if section)
            on_progress(
                {
                    "stage": JobStatus.transcribing,
                    "raw_text": merged_text,
                    "words": len(merged_text.split()),
                    "message": f"{label} 转录完成",
                }
            )

        await asyncio.gather(
            *[
                _transcribe_chunk(index, chunk_path, start, end)
                for index, (chunk_path, start, end) in enumerate(chunks, start=1)
            ]
        )

        return "\n\n".join(section for section in merged_sections if section)
