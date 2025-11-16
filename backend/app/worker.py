import asyncio
import hashlib
import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Callable, Dict, List

import yt_dlp
from sqlalchemy.orm import Session

from .models import Job, JobStatus
from .db import SessionLocal

# simple in-memory subscriber queues per job for WebSocket streaming
subscribers: Dict[str, List[asyncio.Queue]] = {}


def register_queue(job_id: str) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue()
    subscribers.setdefault(job_id, []).append(queue)
    return queue


def unregister_queue(job_id: str, queue: asyncio.Queue):
    if job_id in subscribers:
        subscribers[job_id] = [q for q in subscribers[job_id] if q is not queue]
        if not subscribers[job_id]:
            subscribers.pop(job_id, None)


def broadcast(job_id: str, payload: dict):
    for queue in subscribers.get(job_id, []):
        queue.put_nowait(payload)


async def run_job(job_id: str, url: str, db_factory: Callable[[], Session]):
    db = db_factory()
    job: Job = db.query(Job).get(job_id)
    try:
        await _run(job, url, db)
    except Exception as exc:  # broad catch to mark error
        job.status = JobStatus.error
        job.error = str(exc)
        db.commit()
        broadcast(job_id, {"stage": "error", "message": str(exc)})
    finally:
        db.close()


async def _run(job: Job, url: str, db: Session):
    job.status = JobStatus.downloading
    db.commit()
    logging.info("job %s started, url=%s", job.id, url)
    broadcast(job.id, {"stage": JobStatus.downloading, "message": "Downloading audio"})

    cache_path = get_cache_path(url)

    if cache_path.exists():
        audio_path = cache_path
        broadcast(
            job.id,
            {"stage": JobStatus.downloading, "message": "Cache hit, reuse audio"},
        )
        logging.info("job %s cache hit %s", job.id, audio_path)
    else:
        with tempfile.TemporaryDirectory() as tmpdir:
            target_base = Path(tmpdir) / f"{job.id}"
            downloaded = await download_audio(url, target_base)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(downloaded, cache_path)
            audio_path = cache_path
        logging.info("job %s downloaded to %s", job.id, audio_path)

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file missing: {audio_path}")

    job.status = JobStatus.transcribing
    db.commit()
    broadcast(job.id, {"stage": JobStatus.transcribing, "message": "Transcribing"})

    raw_text = await stream_transcription(audio_path, job.id)
    job.raw_text = raw_text
    logging.info("job %s transcription done, length=%d", job.id, len(raw_text))

    job.status = JobStatus.formatting
    db.commit()
    broadcast(job.id, {"stage": JobStatus.formatting, "message": "Formatting"})

    formatted = await stream_formatting(raw_text, job.id)
    job.formatted_text = formatted
    logging.info("job %s formatting done, length=%d", job.id, len(formatted))

    job.status = JobStatus.done
    db.commit()
    broadcast(job.id, {"stage": JobStatus.done, "message": "Done"})
    logging.info("job %s completed", job.id)


async def download_audio(url: str, target_base: Path) -> Path:
    loop = asyncio.get_event_loop()

    def _download():
        ydl_opts = {
            "extract_audio": True,
            "format": "worstaudio/worst",
            "outtmpl": f"{target_base}.%(ext)s",  # ensure extension placeholder
            "final_ext": "mp3",
            "quiet": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    await loop.run_in_executor(None, _download)

    candidate = find_audio_file(target_base)
    if candidate:
        return candidate

    raise FileNotFoundError(
        f"Audio file not found after download in {target_base.parent}"
    )


def find_audio_file(target_base: Path) -> Path | None:
    # first try exact stem with common audio extensions
    exts = [".mp3", ".m4a", ".aac", ".opus", ".webm", ".wav", ".flac"]
    for ext in exts:
        p = target_base.with_suffix(ext)
        if p.exists():
            return p
    # fallback: newest audio-like file in directory
    audio_glob = list(target_base.parent.glob("*.*"))
    audio_sorted = sorted(
        [p for p in audio_glob if p.suffix.lower() in exts],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if audio_sorted:
        return audio_sorted[0]
    return None


def get_cache_path(url: str) -> Path:
    cache_dir = Path(os.getenv("AUDIO_CACHE_DIR", "./cache"))
    hashed = hashlib.sha256(url.encode()).hexdigest()[:32]
    return cache_dir / f"{hashed}.mp3"


async def stream_transcription(audio_path: Path, job_id: str) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    accumulated = []
    word_count = 0
    with open(audio_path, "rb") as f:
        stream = await client.audio.transcriptions.create(
            file=f,
            model="gpt-4o-mini-transcribe",
            response_format="json",
            stream=True,
        )
        async for event in stream:
            # events documented as transcript.text.delta / .done
            if "delta" in event.type:
                delta = event.delta
                accumulated.append(delta)
                word_count = len("".join(accumulated).split())
                broadcast(
                    job_id,
                    {
                        "stage": JobStatus.transcribing,
                        "words": word_count,
                        "chunk": delta,
                    },
                )
            elif "done" in event.type:
                text = event.text
                logging.info(
                    f"Transcription done event received, input_tokens={event.usage.input_tokens}, output_tokens={event.usage.output_tokens}"
                )
                accumulated = [text]
                # send final full text to front-end to avoid partial leftovers
                broadcast(
                    job_id,
                    {
                        "stage": JobStatus.transcribing,
                        "words": len(text.split()),
                        "raw_text": text,
                    },
                )

    return "".join(accumulated)


async def stream_formatting(raw_text: str, job_id: str) -> str:
    from openai import AsyncOpenAI

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    api_key = os.getenv("DEEPSEEK_API_KEY")
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    messages = [
        {
            "role": "system",
            "content": "You are a transcript formatter. Clean up text, keep meaning, add paragraphs and timestamps if present.",
        },
        {"role": "user", "content": raw_text},
    ]

    stream = await client.chat.completions.create(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        messages=messages,
        stream=True,
    )
    chunks = []
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
            broadcast(
                job_id,
                {"stage": JobStatus.formatting, "words": token_count, "chunk": delta},
            )
    return "".join(chunks)


def create_job_record(url: str, db: Session) -> Job:
    job = Job(id=str(uuid.uuid4()), url=url, status=JobStatus.pending)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def enqueue_job(job: Job):
    loop = asyncio.get_event_loop()
    loop.create_task(run_job(job.id, job.url, SessionLocal))
