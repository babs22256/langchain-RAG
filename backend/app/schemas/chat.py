"""问答相关模型。"""
from typing import Optional

from pydantic import BaseModel


class Citation(BaseModel):
    text: str
    source: str
    doc_id: int
    chunk_index: int
    score: float


class ChatIn(BaseModel):
    session_id: Optional[int] = None
    message: str


class ChatOut(BaseModel):
    session_id: int
    answer: str
    citations: list[Citation]
    retrieve_time: float  # 检索耗时（秒）
    generate_time: float  # 生成耗时（秒）
