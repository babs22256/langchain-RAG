"""知识库分块表：存储每个文档切分后的文本块，用于 BM25 检索与预览。"""
from sqlalchemy import Column, ForeignKey, Integer, Text

from ..database import Base


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, index=True)
    doc_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    chunk_index = Column(Integer, default=0)
    text = Column(Text, nullable=False)
