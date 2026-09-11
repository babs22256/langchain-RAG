"""BM25 关键词检索（纯 Python + jieba 中文分词，带缓存）。

用于与向量检索融合，构成「语义 + 关键词」的混合检索。
索引在知识库发生变化时置为 dirty，下一次查询时惰性重建。
"""
import threading

import jieba
from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session

from ..models.chunk import Chunk

_cache: dict | None = None
_dirty = True
_lock = threading.Lock()


def invalidate() -> None:
    """知识库发生变化后调用，使缓存失效。"""
    global _dirty
    with _lock:
        _dirty = True


def _tokenize(text: str) -> list[str]:
    return [t for t in jieba.lcut(text) if t.strip()]


def _build_index(db: Session) -> dict:
    global _cache, _dirty
    rows = db.query(Chunk.id, Chunk.doc_id, Chunk.chunk_index, Chunk.text).all()
    ids = [r.id for r in rows]
    doc_ids = [r.doc_id for r in rows]
    chunk_indexes = [r.chunk_index for r in rows]
    corpus = [r.text for r in rows]
    tokenized = [_tokenize(t) for t in corpus]
    bm25 = BM25Okapi(tokenized) if tokenized else None
    _cache = {
        "ids": ids,
        "doc_ids": doc_ids,
        "chunk_indexes": chunk_indexes,
        "corpus": corpus,
        "bm25": bm25,
    }
    _dirty = False
    return _cache


def bm25_search(db: Session, query: str, top_k: int = 40) -> list[dict]:
    """返回 [{chunk_id, doc_id, chunk_index, text, score}]。"""
    with _lock:
        index = _cache if (not _dirty and _cache is not None) else _build_index(db)
    bm25 = index["bm25"]
    if bm25 is None:
        return []
    scores = bm25.get_scores(_tokenize(query))
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    results = []
    for i in ranked:
        if scores[i] <= 0:
            break
        results.append(
            {
                "chunk_id": index["ids"][i],
                "doc_id": index["doc_ids"][i],
                "chunk_index": index["chunk_indexes"][i],
                "text": index["corpus"][i],
                "score": float(scores[i]),
            }
        )
        if len(results) >= top_k:
            break
    return results
