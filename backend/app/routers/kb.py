"""知识库管理接口（仅管理员可访问）。"""
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..core.deps import require_admin
from ..database import get_db
from ..models.chunk import Chunk
from ..models.document import KnowledgeDoc
from ..models.user import User
from ..schemas.kb import ChunkOut, DocumentOut, KBStats
from ..services import bm25, cache
from ..services.ingestion import SUPPORTED_EXTENSIONS, ingest_document
from ..services.vector_store import VectorStoreService

router = APIRouter(
    prefix="/kb",
    tags=["知识库管理"],
    dependencies=[Depends(require_admin)],
)


@router.post("/upload", response_model=DocumentOut)
async def upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    filename = file.filename or "未命名"
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型，仅支持：{' / '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )
    content = await file.read()

    doc = KnowledgeDoc(
        name=filename,
        file_type=suffix.lstrip("."),
        size=len(content),
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    try:
        await ingest_document(db, doc.id, filename, content)
        doc.status = "done"
    except Exception as e:
        doc.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"文档处理失败：{e}")
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    return db.query(KnowledgeDoc).order_by(KnowledgeDoc.id.desc()).all()


@router.get("/documents/{doc_id}/chunks", response_model=list[ChunkOut])
def preview_chunks(doc_id: int, db: Session = Depends(get_db)):
    if db.get(KnowledgeDoc, doc_id) is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return (
        db.query(Chunk)
        .filter(Chunk.doc_id == doc_id)
        .order_by(Chunk.chunk_index)
        .all()
    )


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.get(KnowledgeDoc, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    VectorStoreService.get_instance().delete_by_doc(doc_id)
    db.query(Chunk).filter(Chunk.doc_id == doc_id).delete()
    db.delete(doc)
    db.commit()
    bm25.invalidate()
    # 缓存的答案可能整段引用了刚被删除的文档，必须一并失效，避免幽灵引用
    cache.clear()
    return {"detail": "删除成功"}


@router.get("/stats", response_model=KBStats)
def stats(db: Session = Depends(get_db)):
    doc_count = db.query(KnowledgeDoc).count()
    chunk_count = db.query(Chunk).count()
    vector_count = VectorStoreService.get_instance().count()
    return KBStats(
        document_count=doc_count, chunk_count=chunk_count, vector_count=vector_count
    )
