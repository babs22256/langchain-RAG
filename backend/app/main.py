"""FastAPI 应用入口。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  触发模型注册
from .config import settings
from .core.security import hash_password
from .database import Base, SessionLocal, engine
from .models.user import User
from .routers import auth, chat, kb, session


def init_admin() -> None:
    """启动时自动创建管理员账号（admin/123456）。"""
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == settings.ADMIN_USERNAME).first()
        if admin is None:
            db.add(
                User(
                    username=settings.ADMIN_USERNAME,
                    password_hash=hash_password(settings.ADMIN_PASSWORD),
                    role="admin",
                )
            )
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    init_admin()
    yield


app = FastAPI(
    title="RAG 电商知识库问答系统",
    description="基于 LangChain 的企业级 RAG 知识库问答系统",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(kb.router)
app.include_router(chat.router)
app.include_router(session.router)


@app.get("/health", tags=["系统"])
def health():
    return {"status": "ok"}
