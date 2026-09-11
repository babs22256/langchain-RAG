"""会话与消息历史接口。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.deps import get_current_user
from ..database import get_db
from ..models.conversation import Conversation
from ..models.message import Message
from ..models.user import User
from ..schemas.session import MessageOut, SessionOut

router = APIRouter(prefix="/sessions", tags=["会话管理"])


@router.get("", response_model=list[SessionOut])
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )


@router.post("", response_model=SessionOut)
def create_session(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    session = Conversation(user_id=user.id, title="新会话")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/{session_id}/messages", response_model=list[MessageOut])
def list_messages(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.get(Conversation, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status_code=403, detail="会话不存在或无权访问")
    return (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.id)
        .all()
    )


@router.delete("/{session_id}")
def delete_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.get(Conversation, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status_code=403, detail="会话不存在或无权访问")
    db.query(Message).filter(Message.session_id == session_id).delete()
    db.delete(session)
    db.commit()
    return {"detail": "删除成功"}
