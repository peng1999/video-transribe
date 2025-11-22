import logging
from pathlib import Path
from typing import Callable

from openai import AsyncOpenAI

from ..models import JobStatus


async def transcribe(
    audio_path: Path, job_id: str, on_progress: Callable[[dict], None]
) -> str:
    """Stream transcription with OpenAI and forward incremental progress."""
    client = AsyncOpenAI()
    accumulated: list[str] = []
    with open(audio_path, "rb") as f:
        logging.info("job %s starting transcription stream", job_id)
        stream = await client.audio.transcriptions.create(
            file=f,
            model="gpt-4o-mini-transcribe",
            response_format="json",
            stream=True,
        )
        first = True
        async for event in stream:
            if first:
                logging.info("job %s received first transcription event", job_id)
                first = False
            if "delta" in event.type:
                delta = event.delta
                accumulated.append(delta)
                on_progress(
                    {
                        "stage": JobStatus.transcribing,
                        "words": len("".join(accumulated).split()),
                        "chunk": delta,
                    }
                )
            elif "done" in event.type:
                text = event.text
                accumulated = [text]
                on_progress(
                    {
                        "stage": JobStatus.transcribing,
                        "words": len(text.split()),
                        "raw_text": text,
                    }
                )

    return "".join(accumulated)
