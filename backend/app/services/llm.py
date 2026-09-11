"""LLM / Embedding / Rerank 模型工厂。

- LLM：DeepSeek（OpenAI 兼容）
- Embedding：硅基流动 BGE-M3（OpenAI 兼容 /v1/embeddings）
- Reranker：硅基流动 BGE-reranker-v2-m3（/v1/rerank）

性能要点：这三类客户端内部都持有 HTTP 连接池，构造开销大，
每次新建都意味着一次全新的 TCP + TLS 握手。因此这里全部做进程内复用，
高并发下可省去每个请求数次的握手开销。
"""
from functools import lru_cache

import httpx
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from ..config import settings


@lru_cache(maxsize=2)
def get_llm(streaming: bool = False) -> ChatOpenAI:
    """按 streaming 复用 LLM 客户端（连接池共享，可并发调用）。"""
    return ChatOpenAI(
        model=settings.DEEPSEEK_MODEL,
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        temperature=0.3,
        streaming=streaming,
    )


@lru_cache(maxsize=1)
def get_embeddings() -> OpenAIEmbeddings:
    """复用 Embedding 客户端（连接池共享，可并发调用）。"""
    return OpenAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        api_key=settings.SILICONFLOW_API_KEY,
        base_url=settings.SILICONFLOW_BASE_URL,
    )


_rerank_client: httpx.AsyncClient | None = None


def _get_rerank_client() -> httpx.AsyncClient:
    """惰性创建并复用重排专用的异步 HTTP 客户端（避免每请求重建连接池）。"""
    global _rerank_client
    if _rerank_client is None:
        _rerank_client = httpx.AsyncClient(
            timeout=30,
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=100),
        )
    return _rerank_client


async def rerank(query: str, documents: list[str], top_n: int = 5) -> list[dict]:
    """调用硅基流动重排接口，返回 [{index, relevance_score}, ...]。"""
    headers = {"Authorization": f"Bearer {settings.SILICONFLOW_API_KEY}"}
    payload = {
        "model": settings.RERANK_MODEL,
        "query": query,
        "documents": documents,
        "top_n": top_n,
        "return_documents": False,
    }
    resp = await _get_rerank_client().post(
        f"{settings.SILICONFLOW_BASE_URL}/rerank", json=payload, headers=headers
    )
    resp.raise_for_status()
    return resp.json().get("results", [])
