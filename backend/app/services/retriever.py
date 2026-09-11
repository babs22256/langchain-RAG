"""混合检索：向量检索 + BM25 关键词检索，RRF 融合后重排。

流程：向量 top-40 + BM25 top-40 -> RRF 融合 -> 取 top-30 -> BGE-reranker 精排 -> top-5
"""
import asyncio

from sqlalchemy.orm import Session

from ..models.document import KnowledgeDoc
from . import bm25
from .llm import get_embeddings, rerank
from .vector_store import VectorStoreService

VECTOR_TOP_K = 40
BM25_TOP_K = 40
FUSED_TOP_K = 30
RERANK_TOP_K = 5
RRF_K = 60


def _rrf_fuse(vector_hits: list[dict], bm25_hits: list[dict], k: int = RRF_K) -> list[dict]:
    """Reciprocal Rank Fusion：按排名倒数求和，融合两个检索结果。"""
    fused: dict[tuple, dict] = {}

    def add(hit: dict, rank: int, label: str) -> None:
        key = (int(hit["doc_id"]), int(hit["chunk_index"]))
        entry = fused.get(key)
        if entry is None:
            entry = {
                "doc_id": int(hit["doc_id"]),
                "chunk_index": int(hit["chunk_index"]),
                "text": hit["text"],
                "rrf": 0.0,
            }
            fused[key] = entry
        entry["rrf"] += 1.0 / (k + rank)
        entry[f"{label}_score"] = float(hit["score"])

    for rank, hit in enumerate(vector_hits, start=1):
        add(hit, rank, "vector")
    for rank, hit in enumerate(bm25_hits, start=1):
        add(hit, rank, "bm25")

    return sorted(fused.values(), key=lambda x: x["rrf"], reverse=True)


def _doc_name_map(db: Session) -> dict[int, str]:
    rows = db.query(KnowledgeDoc.id, KnowledgeDoc.name).all()
    return {r.id: r.name for r in rows}


async def retrieve(db: Session, query: str, top_k: int = RERANK_TOP_K) -> list[dict]:
    """执行混合检索与重排，返回带来源信息的片段列表。"""
    embeddings = get_embeddings()
    # 查询向量化（网络调用，放线程池）
    query_vector = await asyncio.to_thread(embeddings.embed_query, query)

    store = VectorStoreService.get_instance()
    vector_hits = store.search(query_vector, top_k=VECTOR_TOP_K)
    bm25_hits = bm25.bm25_search(db, query, top_k=BM25_TOP_K)

    fused = _rrf_fuse(vector_hits, bm25_hits)[:FUSED_TOP_K]
    if not fused:
        return []

    # 数据库读取到此为止：先取好来源文档名，随即结束只读事务，把连接还给连接池。
    # 否则 SQLAlchemy 会一直持有这条连接直到调用方下一次 commit —— 而紧随其后的
    # rerank 以及调用方的 LLM 流式生成长达数十秒，100 并发会直接耗尽连接池。
    # 前置条件：调用方进入本函数前已完成写入提交（见 routers/chat.py）。
    doc_names = _doc_name_map(db)
    db.rollback()

    # 重排精排
    documents = [h["text"] for h in fused]
    try:
        results = await rerank(query, documents, top_n=min(top_k, len(documents)))
    except Exception:
        # 重排失败则退化为 RRF 顺序，保证系统可用
        results = [
            {"index": i, "relevance_score": 0.0}
            for i in range(min(top_k, len(documents)))
        ]

    final: list[dict] = []
    for r in results:
        idx = r["index"]
        if idx >= len(fused):
            continue
        hit = fused[idx]
        final.append(
            {
                "text": hit["text"],
                "doc_id": hit["doc_id"],
                "chunk_index": hit["chunk_index"],
                "source": doc_names.get(hit["doc_id"], "未知文档"),
                "score": round(float(r.get("relevance_score", 0.0)), 4),
            }
        )
    return final
