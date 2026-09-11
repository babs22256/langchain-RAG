"""知识库问答接口：非流式与 SSE 流式。"""
import asyncio
import json
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..core.deps import get_current_user
from ..database import get_db
from ..models.conversation import Conversation
from ..models.message import Message
from ..models.user import User
from ..schemas.chat import ChatIn, ChatOut, Citation
from ..services import cache, retriever
from ..services.rag_chain import build_prompt, generate, generate_stream_async

router = APIRouter(prefix="/chat", tags=["知识库问答"])

HISTORY_LIMIT = 6  # 生成时携带最近 N 条历史


def _get_or_create_session(
    db: Session, user_id: int, session_id: int | None, first_message: str
) -> Conversation:
    if session_id is not None:
        session = db.get(Conversation, session_id)
        if session is None or session.user_id != user_id:
            raise HTTPException(status_code=403, detail="会话不存在或无权访问")
        return session
    title = first_message.strip()[:20] or "新会话"
    session = Conversation(user_id=user_id, title=title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _load_history(db: Session, session_id: int, limit: int) -> list[dict]:
    msgs = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.id.desc())
        .limit(limit)
        .all()
    )
    msgs.reverse()
    return [{"role": m.role, "content": m.content} for m in msgs]


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("", response_model=ChatOut)
async def chat(
    data: ChatIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """非流式问答（保留用于简单调用与接口调试）。"""
    question = data.message.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    session = _get_or_create_session(db, user.id, data.session_id, question)
    session_id = session.id  # 提前取出：检索释放连接后 ORM 对象会过期
    history = _load_history(db, session_id, HISTORY_LIMIT)

    db.add(Message(session_id=session_id, role="user", content=question))
    session.updated_at = datetime.now(timezone.utc)
    db.commit()

    t0 = time.perf_counter()
    docs = await retriever.retrieve(db, question)
    retrieve_time = time.perf_counter() - t0

    messages = build_prompt(question, docs, history)
    t1 = time.perf_counter()
    answer = await asyncio.to_thread(generate, messages)
    generate_time = time.perf_counter() - t1

    citations = [
        Citation(
            text=d["text"],
            source=d["source"],
            doc_id=d["doc_id"],
            chunk_index=d["chunk_index"],
            score=d["score"],
        )
        for d in docs
    ]
    db.add(
        Message(
            session_id=session_id,
            role="assistant",
            content=answer,
            citations=json.dumps(
                [c.model_dump() for c in citations], ensure_ascii=False
            ),
        )
    )
    db.query(Conversation).filter(Conversation.id == session_id).update(
        {"updated_at": datetime.now(timezone.utc)}
    )
    db.commit()

    return ChatOut(
        session_id=session_id,
        answer=answer,
        citations=citations,
        retrieve_time=round(retrieve_time, 3),
        generate_time=round(generate_time, 3),
    )


@router.post("/stream")
async def chat_stream(
    data: ChatIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """SSE 流式问答：先返回引用片段（meta），再逐字返回回答（token）。"""
    question = data.message.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    session = _get_or_create_session(db, user.id, data.session_id, question)
    session_id = session.id  # 提前取出：检索释放连接后 ORM 对象会过期
    history = _load_history(db, session_id, HISTORY_LIMIT)

    db.add(Message(session_id=session_id, role="user", content=question))
    session.updated_at = datetime.now(timezone.utc)
    db.commit()

    async def gen():
        citations: list[Citation] = []
        retrieve_time = 0.0
        generate_time = 0.0
        answer = ""
        cached = cache.get(question)

        if cached is not None:
            # 命中缓存：直接返回完整答案
            answer = cached["answer"]
            citations = [Citation(**c) for c in cached["citations"]]
            retrieve_time = cached["retrieve_time"]
            generate_time = cached["generate_time"]
            yield _sse(
                "meta",
                {
                    "session_id": session_id,
                    "citations": [c.model_dump() for c in citations],
                    "retrieve_time": retrieve_time,
                },
            )
            yield _sse("token", {"text": answer})
        else:
            t0 = time.perf_counter()
            docs = await retriever.retrieve(db, question)
            retrieve_time = round(time.perf_counter() - t0, 3)
            citations = [
                Citation(
                    text=d["text"],
                    source=d["source"],
                    doc_id=d["doc_id"],
                    chunk_index=d["chunk_index"],
                    score=d["score"],
                )
                for d in docs
            ]
            yield _sse(
                "meta",
                {
                    "session_id": session_id,
                    "citations": [c.model_dump() for c in citations],
                    "retrieve_time": retrieve_time,
                },
            )

            messages = build_prompt(question, docs, history)
            parts: list[str] = []
            t1 = time.perf_counter()
            async for chunk in generate_stream_async(messages):
                parts.append(chunk)
                yield _sse("token", {"text": chunk})
            generate_time = round(time.perf_counter() - t1, 3)
            answer = "".join(parts)

            cache.set(
                question,
                {
                    "answer": answer,
                    "citations": [c.model_dump() for c in citations],
                    "retrieve_time": retrieve_time,
                    "generate_time": generate_time,
                },
            )

        # 持久化回答与引用
        db.add(
            Message(
                session_id=session_id,
                role="assistant",
                content=answer,
                citations=json.dumps(
                    [c.model_dump() for c in citations], ensure_ascii=False
                ),
            )
        )
        db.query(Conversation).filter(Conversation.id == session_id).update(
            {"updated_at": datetime.now(timezone.utc)}
        )
        db.commit()

        yield _sse("done", {"generate_time": generate_time, "cached": cached is not None})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
