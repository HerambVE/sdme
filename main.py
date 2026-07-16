from celery.result import AsyncResult
from models import MediaAnalysis,Base,engine
from worker import analyse_media_drift,celery_app
from database import AsyncSessionLocal
from pydantic import BaseModel
from sqlalchemy import select
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime,timezone
from contextlib import asynccontextmanager

class req(BaseModel):
    media_url: list[str]
    
@asynccontextmanager    
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("Database schema successfully generated")
    yield   
    await engine.dispose()
    print("Database connection pool safely closed")

app = FastAPI(
    title="Semantic Drift Media Engine",
    lifespan = lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credential=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/process-media/",status_code=status.HTTP_202_ACCEPTED)
async def post_method(payload: req):
    task = analyse_media_drift.delay(payload.media_url)
    return {"status" : "Task Queued","Task_id" : task.id}

@app.get("/task-status/{task_id}", status_code=status.HTTP_200_OK)
async def get_method(task_id : str):
    result = AsyncResult(task_id,app=celery_app)
    response = {
        "task_id": task_id,
        "task_status": result.status,
        "result": None
    }
    if result.status == "SUCCESS":
        async with AsyncSessionLocal() as Session:
            async with Session.begin():
                query = select(MediaAnalysis).where(MediaAnalysis.task_id == task_id)
                phrase = await Session.execute(query)
                analysis = phrase.scalar_one_or_none()
                if analysis:
                    analysis.result_payload = result.result
                    analysis.status_timestamp = datetime.now(timezone.utc)
                    print(f"Task {task_id} updated.")
                else:
                    # ... [inside your main.py GET endpoint] ...
                    derived_media_url = ""
                    if isinstance(result.result, dict) and "Name" in result.result:
                        derived_media_url = result.result.get("Name")
                    elif isinstance(result.result, list) and len(result.result) > 0:
                        # Fallback to empty string instead of integer 0
                        derived_media_url = result.result[0].get("Name", "")

                    analysis = MediaAnalysis(
                        task_id=task_id,
                        media_reference=derived_media_url
                    )
                    Session.add(analysis)
                    print(f"Task {task_id} created.")
        response["result"] = result.result
    elif result.status == "FAILURE":
        response["result"] = str(result.result)
    elif result.status == "PENDING":
        response["result"] = "Task is pending a worker or does not exist"
    
    return response