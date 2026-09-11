"""文档解析、分块、向量化入库。"""
import asyncio
import io
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.orm import Session

from ..models.chunk import Chunk
from ..models.document import KnowledgeDoc
from . import bm25
from .llm import get_embeddings
from .vector_store import VectorStoreService

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
EMBED_BATCH = 32


def parse_file(filename: str, content: bytes) -> str:
    """按扩展名解析文件为纯文本。"""
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if suffix == ".docx":
        from docx import Document as DocxDocument

        doc = DocxDocument(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)
    if suffix in {".txt", ".md"}:
        return content.decode("utf-8", errors="ignore")
    raise ValueError(f"不支持的文件类型: {suffix}")


def split_text(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
    )
    return splitter.split_text(text)


def _embed_all(texts: list[str]) -> list[list[float]]:
    """批量向量化（网络调用，放到线程池执行）。"""
    embeddings = get_embeddings()
    vectors: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        vectors.extend(embeddings.embed_documents(texts[i : i + EMBED_BATCH]))
    return vectors


async def ingest_document(db: Session, doc_id: int, filename: str, content: bytes) -> None:
    """解析 -> 分块 -> 向量化 -> 写入 SQLite 与 Milvus。"""
    text = parse_file(filename, content)
    chunks = split_text(text)
    if not chunks:
        raise ValueError("文档内容为空或无法解析")

    # 向量化是网络调用，放到线程池避免阻塞事件循环
    vectors = await asyncio.to_thread(_embed_all, chunks)

    # 分块写入 SQLite（用于 BM25 与预览）
    for i, chunk_text in enumerate(chunks):
        db.add(Chunk(doc_id=doc_id, chunk_index=i, text=chunk_text))

    doc = db.get(KnowledgeDoc, doc_id)
    if doc is not None:
        doc.chunk_count = len(chunks)

    # 向量写入 Milvus Lite
    VectorStoreService.get_instance().add(
        vectors=vectors,
        texts=chunks,
        doc_ids=[doc_id] * len(chunks),
        chunk_indexes=list(range(len(chunks))),
    )

    # 使 BM25 缓存失效
    bm25.invalidate()
