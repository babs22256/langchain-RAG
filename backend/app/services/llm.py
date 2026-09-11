"""LLM / Embedding / Rerank 模型工厂。

- LLM：DeepSeek（OpenAI 兼容）
- Embedding：硅基流动 BGE-M3（OpenAI 兼容 /v1/embeddings）
- Reranker：硅基流动 BGE-reranker-v2-m3（/v1/rerank）
"""
import httpx
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from ..config import settings


def get_llm(streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.DEEPSEEK_MODEL,
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        temperature=0.3,
        streaming=streaming,
    )


def get_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        api_key=settings.SILICONFLOW_API_KEY,
        base_url=settings.SILICONFLOW_BASE_URL,
    )


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
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.SILICONFLOW_BASE_URL}/rerank", json=payload, headers=headers
        )
        resp.raise_for_status()
        data = resp.json()
    return data.get("results", [])
