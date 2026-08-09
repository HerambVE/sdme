import os
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import delete

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./media_engine.db")


# connect_args disables thread checking (required for SQLite in async contexts)
engine = create_async_engine(
    DATABASE_URL, 
    echo=False, 
    connect_args={"check_same_thread": False}
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False
)

Base = declarative_base()

def remove_database_file():
    db_path = "media_engine.db"
    if "sqlite" in DATABASE_URL:
        parts = DATABASE_URL.split(":///")
        if len(parts) > 1:
            db_path = parts[-1]

    for suffix in ["", "-wal", "-shm", "-journal"]:
        target = f"{db_path}{suffix}"
        if os.path.exists(target):
            try:
                os.remove(target)
                print(f"[DB CLEANUP] Removed {target}")
            except Exception as e:
                print(f"[DB CLEANUP] Failed to remove {target}: {e}")


async def purge_stale_records(days_to_keep: int = 30):
    # Local import prevents circular dependency with models.py
    from models import MediaAnalysis 
    
    async with AsyncSessionLocal() as session:
        async with session.begin():
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
            
            # Execute atomic asynchronous bulk delete
            query = delete(MediaAnalysis).where(MediaAnalysis.status_timestamp < cutoff_date)
            result = await session.execute(query)
            return result.rowcount