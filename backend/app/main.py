import asyncio
import logging
import os
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .models import Job, JobStatus
from .schemas import CreateJobRequest, JobResponse, JobsResponse
from .worker import (
    broadcast,
    create_job_record,
    enqueue_job,
    register_queue,
    unregister_queue,
)

load_dotenv()
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Bilibili Transcriber", version="0.1.0", root_path="/api")

origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/jobs", response_model=JobResponse)
async def create_job(body: CreateJobRequest, db: Session = Depends(get_db)):
    if "bilibili.com" not in body.url.host:
        raise HTTPException(status_code=400, detail="仅允许 bilibili 链接")

    job = create_job_record(str(body.url), db)
    enqueue_job(job)
    return job


@app.get("/api/jobs", response_model=JobsResponse)
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.query(Job).order_by(Job.created_at.desc()).limit(50).all()
    return JobsResponse(jobs=jobs)


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Not found")
    return job


@app.websocket("/api/ws/jobs/{job_id}")
async def job_ws(websocket: WebSocket, job_id: str, db: Session = Depends(get_db)):
    await websocket.accept()
    queue = register_queue(job_id)

    job = db.query(Job).get(job_id)
    if not job:
        await websocket.send_json({"error": "not found"})
        await websocket.close()
        unregister_queue(job_id, queue)
        return

    # send current snapshot
    await websocket.send_json(
        {
            "stage": job.status,
            "raw_text": job.raw_text,
            "formatted_text": job.formatted_text,
        }
    )

    try:
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        unregister_queue(job_id, queue)
    except Exception as exc:
        unregister_queue(job_id, queue)
        await websocket.close(code=1011, reason=str(exc))


@app.get("/")
async def root():
    return {"message": "Bilibili transcriber backend running"}
