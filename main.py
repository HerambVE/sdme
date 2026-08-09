from celery.result import AsyncResult
from models import MediaAnalysis
from worker import analyse_media_drift, celery_app
from database import AsyncSessionLocal, Base, engine, purge_stale_records, remove_database_file
from pydantic import BaseModel
from sqlalchemy import select
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
import asyncio
import os


class req(BaseModel):
    media_url: list[str]
    force_reanalyse: bool = False

    
async def background_cleanup_loop():
    while True:
        try:
            await purge_stale_records(days_to_keep=30)
        except Exception as e:
            print(f"Cleanup cycle failed: {e}")
        await asyncio.sleep(86400)

@asynccontextmanager    
async def lifespan(app: FastAPI):
    if os.getenv("REMOVE_DB_ON_STARTUP", "true").lower() in ("true", "1", "yes"):
        print("[DB LIFESPAN] Purging previous database file on startup...")
        remove_database_file()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("Database schema successfully generated")
    
    cleanup_task = asyncio.create_task(background_cleanup_loop())
    
    yield   
    
    cleanup_task.cancel()
    await engine.dispose()
    print("Database connection pool safely closed")

    if os.getenv("REMOVE_DB_ON_SHUTDOWN", "true").lower() in ("true", "1", "yes"):
        print("[DB LIFESPAN] Removing database file on shutdown...")
        remove_database_file()


app = FastAPI(
    title="Semantic Drift Media Engine",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request, exc):
    if exc.status_code == 404:
        for page in ["404.html", "_not-found.html", "index.html"]:
            filepath = os.path.join("out", page)
            if os.path.exists(filepath):
                return FileResponse(filepath, status_code=200)
    return exc

@app.get("/health/", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "ok", "service": "SDME Engine"}



from fastapi import FastAPI, status, Request

@app.post("/process-media/", status_code=status.HTTP_202_ACCEPTED)
async def post_method(payload: req, request: Request):
    target_media_reference = payload.media_url[0] if payload.media_url else ""
    # Extract user-provided custom API key from HTTP header (RAM transient only, never persisted)
    user_api_key = request.headers.get("x-gemini-api-key") or request.headers.get("X-Gemini-API-Key")
    
    async with AsyncSessionLocal() as session:
        # 1. Database-Level Idempotency Check
        query = select(MediaAnalysis).where(MediaAnalysis.media_reference == target_media_reference)
        result = await session.execute(query)
        existing_record = result.scalars().first()
        
        if existing_record:
            # If user explicitly requested forced re-analysis, invalidate cache and re-dispatch task
            if payload.force_reanalyse:
                task = analyse_media_drift.delay(payload.media_url, custom_api_key=user_api_key)
                existing_record.task_id = task.id
                existing_record.result_payload = None
                existing_record.status_timestamp = datetime.now(timezone.utc)
                await session.commit()
                return {"status": "Task Re-Queued (Forced Re-Analysis)", "Task_id": task.id}

            # Return cached result if already completed and force_reanalyse is False
            if existing_record.result_payload is not None:
                return {
                    "status": "Already Processed", 
                    "Task_id": existing_record.task_id,
                    "data": existing_record.result_payload
                }
            
            celery_state = AsyncResult(existing_record.task_id, app=celery_app).status
            
            if celery_state in ["PENDING", "STARTED"]:
                # Ensure timezone awareness for calculation
                record_time = existing_record.status_timestamp
                if record_time.tzinfo is None:
                    record_time = record_time.replace(tzinfo=timezone.utc)
                
                # Assess task staleness to identify orphaned tasks from previous docker lifecycles
                time_elapsed = datetime.now(timezone.utc) - record_time
                
                if time_elapsed > timedelta(minutes=30):
                    task = analyse_media_drift.delay(payload.media_url, custom_api_key=user_api_key)
                    existing_record.task_id = task.id
                    existing_record.status_timestamp = datetime.now(timezone.utc)
                    await session.commit()
                    return {"status": "Task Re-Queued (Recovered Orphan)", "Task_id": task.id}
                else:
                    return {
                        "status": "Task Currently Processing", 
                        "Task_id": existing_record.task_id
                    }
            
            # If task failed explicitly, re-dispatch to Celery
            task = analyse_media_drift.delay(payload.media_url, custom_api_key=user_api_key)
            existing_record.task_id = task.id
            existing_record.status_timestamp = datetime.now(timezone.utc)
            await session.commit()
            return {"status": "Task Re-Queued", "Task_id": task.id}

        # 2. Dispatch to worker if no record exists
        task = analyse_media_drift.delay(payload.media_url, custom_api_key=user_api_key)
        
        new_analysis_job = MediaAnalysis(
            task_id=task.id,
            media_reference=target_media_reference,
            status_timestamp=datetime.now(timezone.utc)
        )
        session.add(new_analysis_job)
        await session.commit()
        
    return {"status": "Task Queued", "Task_id": task.id}


@app.get("/task-status/{task_id}", status_code=status.HTTP_200_OK)
async def get_method(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    response = {
        "Task_id": task_id,
        "task_status": result.status,
        "result": None
    }
    
    if result.status == "SUCCESS":
        async with AsyncSessionLocal() as session:
            async with session.begin():
                query = select(MediaAnalysis).where(MediaAnalysis.task_id == task_id)
                phrase = await session.execute(query)
                analysis = phrase.scalars().first()
                
                if analysis:
                    analysis.result_payload = result.result
                    analysis.status_timestamp = datetime.now(timezone.utc)
                    print(f"Task {task_id} updated.")
                else:
                    derived_media_url = ""
                    if isinstance(result.result, dict) and "Name" in result.result:
                        derived_media_url = result.result.get("Name")
                    elif isinstance(result.result, list) and len(result.result) > 0:
                        derived_media_url = result.result[0].get("Name", "")

                    analysis = MediaAnalysis(
                        task_id=task_id,
                        media_reference=derived_media_url,
                        result_payload=result.result,
                        status_timestamp=datetime.now(timezone.utc)
                    )
                    session.add(analysis)
                    print(f"Task {task_id} created.")
        response["result"] = result.result
    elif result.status == "FAILURE":
        response["result"] = str(result.result)
    elif result.status == "PENDING":
        response["result"] = "Task is pending a worker or does not exist"
    
    return response

# Serve static frontend files from Next.js export directory ('out') at '/'
os.makedirs("out", exist_ok=True)
app.mount("/", StaticFiles(directory="out", html=True), name="static")