import asyncio
import hashlib
import logging
import os
import shutil
import tempfile
import uuid
from contextlib import chdir
from pathlib import Path
from typing import Callable

import yt_dlp
from sqlalchemy.orm import Session

from .models import Job, JobStatus
from .db import SessionLocal
from .providers import (
    transcribe_with_openai,
    transcribe_with_bailian,
    stream_formatting,
    DEFAULT_BAILIAN_MODEL,
)

# simple in-memory subscriber queues per job for WebSocket streaming
subscribers: dict[str, list[asyncio.Queue]] = {}
# store latest payload per job so late subscribers can catch up
latest_payload: dict[str, dict] = {}


def update_snapshot(job_id: str, payload: dict):
    base = latest_payload.get(job_id, {})
    # Late joiners shouldn't reapply the last streamed chunk (frontend already has formatted_text).
    snapshot_payload = {k: v for k, v in payload.items() if k != "chunk"}
    latest_payload[job_id] = {**base, **snapshot_payload}


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
    # merge payload into latest snapshot for late joiners
    update_snapshot(job_id, payload)
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
    # helper to adapt provider callbacks (payload-only) to our broadcaster
    def _progress(payload: dict):
        broadcast(job.id, payload)

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

    provider = job.provider or "openai"
    if provider == "bailian":
        bailian_model = job.model or DEFAULT_BAILIAN_MODEL
        raw_text = await transcribe_with_bailian(
            audio_path,
            job.id,
            on_progress=_progress,
            on_task_id=lambda task_id: _persist_task_id(db, job.id, task_id),
            model=bailian_model,
        )
    else:
        raw_text = await transcribe_with_openai(audio_path, job.id, _progress)
    job.raw_text = raw_text
    logging.info("job %s transcription done, length=%d", job.id, len(raw_text))

    job.status = JobStatus.formatting
    db.commit()
    broadcast(job.id, {"stage": JobStatus.formatting, "message": "Formatting"})

    formatted = await stream_formatting(raw_text, job.id, _progress)
    job.formatted_text = formatted
    logging.info("job %s formatting done, length=%d", job.id, len(formatted))

    job.status = JobStatus.done
    db.commit()
    broadcast(job.id, {"stage": JobStatus.done, "message": "Done"})
    logging.info("job %s completed", job.id)


async def download_audio(url: str, target_base: Path) -> Path:
    loop = asyncio.get_event_loop()

    def _download():
        target_base.parent.mkdir(parents=True, exist_ok=True)
        with chdir(target_base.parent):
            ydl_opts = {
                "extract_audio": True,
                "format": "worstaudio/worst",
                "outtmpl": f"{target_base.name}.%(ext)s",  # ensure extension placeholder
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
    parent = target_base.parent
    if not parent.exists():
        return None
    audio_candidates: list[Path] = []
    for root, dirs, files in parent.walk():
        audio_candidates.extend(
            Path(root) / name for name in files if Path(name).suffix.lower() in exts
        )
        dirs[:] = []  # single-level scan to mirror previous glob scope
        break

    if audio_candidates:
        return max(audio_candidates, key=lambda p: p.stat().st_mtime)
    return None


def get_cache_path(url: str) -> Path:
    cache_dir = Path(os.getenv("AUDIO_CACHE_DIR", "./cache"))
    hashed = hashlib.sha256(url.encode()).hexdigest()[:32]
    return cache_dir / f"{hashed}.mp3"


def create_job_record(
    url: str, provider: str, db: Session, model: str | None = None
) -> Job:
    chosen_provider = provider or os.getenv("DEFAULT_PROVIDER", "openai")
    chosen_model = model
    if chosen_provider == "bailian":
        chosen_model = model or DEFAULT_BAILIAN_MODEL
    job = Job(
        id=str(uuid.uuid4()),
        url=url,
        provider=chosen_provider,
        model=chosen_model,
        status=JobStatus.pending,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def enqueue_job(job: Job):
    loop = asyncio.get_event_loop()
    loop.create_task(run_job(job.id, job.url, SessionLocal))


def _persist_task_id(db: Session, job_id: str, task_id: str):
    job = db.query(Job).get(job_id)
    if not job:
        return
    job.bailian_task_id = task_id
    db.commit()
