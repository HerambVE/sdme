from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import delete

DATABASE_URL = "sqlite+aiosqlite:///./media_engine.db"

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