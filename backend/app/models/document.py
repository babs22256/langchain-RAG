"""知识库文档表：记录已上传文档的元信息。"""
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from ..database import Base


class KnowledgeDoc(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # pdf | docx | txt | md
    size = Column(Integer, default=0)  # 字节
    chunk_count = Column(Integer, default=0)
    status = Column(String, default="pending")  # pending | done | failed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
