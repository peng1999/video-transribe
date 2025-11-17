import asyncio
import logging
import os
from dotenv import load_dotenv
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .db import Base, engine, get_db, SessionLocal
from .models import Job, JobStatus
from .schemas import CreateJobRequest, JobResponse, JobsResponse
from .worker import (
    create_job_record,
    enqueue_job,
    broadcast,
    stream_formatting,
    register_queue,
    unregister_queue,
)

load_dotenv()
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Bilibili Transcriber", version="0.1.0")

origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/jobs", response_model=JobResponse)
async def create_job(
    body: CreateJobRequest, request: Request, db: Session = Depends(get_db)
):
    if "bilibili.com" not in body.url.host:
        raise HTTPException(status_code=400, detail="仅允许 bilibili 链接")

    cf_email = request.headers.get("Cf-Access-Authenticated-User-Email")
    if cf_email:
        logging.info("create_job by CF user: %s", cf_email)
        # TODO: remove this hardcode
        if cf_email != "pg999w@gmail.com":
            raise HTTPException(status_code=403, detail="仅允许管理员创建请求")
    else:
        logging.warning("create_job without CF user email")

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


@app.post("/api/jobs/{job_id}/regenerate", response_model=JobResponse)
async def regenerate_formatted_text(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Not found")
    if job.status in {
        JobStatus.downloading,
        JobStatus.transcribing,
        JobStatus.formatting,
        JobStatus.pending,
    }:
        raise HTTPException(status_code=400, detail="任务正在进行中，无法重新整理")
    if not job.raw_text:
        raise HTTPException(status_code=400, detail="缺少原始转录，无法重新整理")

    job.status = JobStatus.formatting
    job.formatted_text = None
    job.error = None
    db.commit()
    broadcast(job_id, {"stage": JobStatus.formatting, "message": "重新整理中"})

    async def _regenerate():
        db_task = SessionLocal()
        try:
            job_task = db_task.query(Job).get(job_id)
            if not job_task:
                broadcast(job_id, {"stage": JobStatus.error, "error": "任务不存在"})
                return
            formatted = await stream_formatting(job.raw_text or "", job_id)
            job_task.formatted_text = formatted
            job_task.status = JobStatus.done
            db_task.commit()
            broadcast(
                job_id,
                {
                    "stage": JobStatus.done,
                    "formatted_text": formatted,
                    "message": "重新整理完成",
                },
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logging.exception("regenerate job %s failed", job_id)
            job_task = db_task.query(Job).get(job_id)
            if job_task:
                job_task.status = JobStatus.error
                job_task.error = str(exc)
                db_task.commit()
            broadcast(job_id, {"stage": JobStatus.error, "error": str(exc)})
        finally:
            db_task.close()

    asyncio.create_task(_regenerate())
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
