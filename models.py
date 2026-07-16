from datetime import datetime,timezone
from sqlalchemy import Column,Integer,String,DateTime,JSON
from database import Base,engine

class MediaAnalysis(Base):
    __tablename__ = "media_analysis"
    
    id = Column(Integer,primary_key=True,index=True)
    task_id = Column(String, index=True,nullable=False)
    media_reference = Column(String,index=False)
    status_timestamp= Column(DateTime, default=lambda:datetime.now(timezone.utc),nullable=False)
    result_payload = Column(JSON,nullable=True)