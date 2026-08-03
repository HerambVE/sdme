from celery.result import AsyncResult
from models import MediaAnalysis
from worker import analyse_media_drift, celery_app
from database import AsyncSessionLocal, Base, engine, purge_stale_records
from pydantic import BaseModel
from sqlalchemy import select
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
from contextlib import asynccontextmanager
import asyncio

class req(BaseModel):
    media_url: list[str]
    
async def background_cleanup_loop():
    while True:
        try:
            await purge_stale_records(days_to_keep=30)
        except Exception as e:
            print(f"Cleanup cycle failed: {e}")
        await asyncio.sleep(86400)

@asynccontextmanager    
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("Database schema successfully generated")
    
    cleanup_task = asyncio.create_task(background_cleanup_loop())
    
    yield   
    
    cleanup_task.cancel()
    await engine.dispose()
    print("Database connection pool safely closed")

app = FastAPI(
    title="Semantic Drift Media Engine",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/process-media/", status_code=status.HTTP_202_ACCEPTED)
async def post_method(payload: req):
    target_media_reference = payload.media_url[0] if payload.media_url else ""
    
    async with AsyncSessionLocal() as session:
        # 1. Database-Level Idempotency Check
        query = select(MediaAnalysis).where(MediaAnalysis.media_reference == target_media_reference)
        result = await session.execute(query)
        existing_record = result.scalars().first()
        
        if existing_record:
            # Return cached result if already completed
            if existing_record.result_payload is not None:
                return {
                    "status": "Already Processed", 
                    "Task_id": existing_record.task_id,
                    "data": existing_record.result_payload
                }
            
            # Check if active task in Celery
            celery_state = AsyncResult(existing_record.task_id, app=celery_app).status
            if celery_state in ["PENDING", "STARTED"]:
                return {
                    "status": "Task Currently Processing", 
                    "Task_id": existing_record.task_id
                }
            
            # If task failed/stalled, re-dispatch to Celery
            task = analyse_media_drift.delay(payload.media_url)
            existing_record.task_id = task.id
            existing_record.status_timestamp = datetime.now(timezone.utc)
            await session.commit()
            return {"status": "Task Re-Queued", "Task_id": task.id}

        # 2. Dispatch to worker if no record exists
        task = analyse_media_drift.delay(payload.media_url)
        
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