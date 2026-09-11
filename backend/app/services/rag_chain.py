"""RAG 问答链：组装上下文 -> 构建 Prompt -> LLM 生成。"""
from langchain_core.messages import HumanMessage, SystemMessage

from .llm import get_llm

SYSTEM_PROMPT = """你是一个电商平台的智能客服，负责基于商品知识库回答用户关于商品的问题。

请严格遵守以下规则：
1. 优先依据下面提供的【知识库片段】回答问题，不要编造片段中没有的信息。
2. 回答时用 [1][2] 这样的编号标注你所引用的知识片段来源。
3. 如果知识库中没有相关内容，请明确告知用户「知识库中暂未收录相关信息」，不要臆测。
4. 回答简洁、准确、有条理。"""


def build_prompt(question: str, context_docs: list[dict], history: list[dict]) -> list:
    """组装系统提示词与用户提示词。"""
    context_parts = []
    for i, doc in enumerate(context_docs, start=1):
        context_parts.append(
            f"[{i}] 来源：{doc['source']}（第 {doc['chunk_index'] + 1} 段）\n{doc['text']}"
        )
    context = "\n\n".join(context_parts) if context_parts else "（无相关片段）"

    history_parts = []
    for msg in history:
        role = "用户" if msg["role"] == "user" else "客服"
        history_parts.append(f"{role}：{msg['content']}")
    history_text = "\n".join(history_parts) if history_parts else "（无历史对话）"

    system = SystemMessage(content=SYSTEM_PROMPT)
    user = HumanMessage(
        content=(
            f"【知识库片段】\n{context}\n\n"
            f"【历史对话】\n{history_text}\n\n"
            f"【用户问题】\n{question}"
        )
    )
    return [system, user]


def generate(messages: list) -> str:
    """非流式生成。"""
    llm = get_llm(streaming=False)
    resp = llm.invoke(messages)
    return resp.content


def generate_stream(messages: list):
    """流式生成，逐段 yield 文本（同步版，供非异步场景使用）。"""
    llm = get_llm(streaming=True)
    for chunk in llm.stream(messages):
        if chunk.content:
            yield chunk.content


async def generate_stream_async(messages: list):
    """异步流式生成，逐段 yield 文本（用于 SSE 流式响应）。"""
    llm = get_llm(streaming=True)
    async for chunk in llm.astream(messages):
        if chunk.content:
            yield chunk.content
