"""知识库相关模型。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    file_type: str
    size: int
    chunk_count: int
    status: str
    created_at: Optional[datetime] = None


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chunk_index: int
    text: str


class KBStats(BaseModel):
    document_count: int
    chunk_count: int
    vector_count: int
