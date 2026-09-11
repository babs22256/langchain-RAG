"""SQLAlchemy 数据库引擎与会话。"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

# SQLite 需要关闭同线程检查，否则 FastAPI 多线程访问会报错；
# timeout 让写锁冲突时等待而不是立刻失败。
connect_args = {"check_same_thread": False, "timeout": 15} if _is_sqlite else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    # SQLAlchemy 默认 QueuePool 仅 5 + 10 = 15 条连接，
    # 高并发下请求会在池中排队直到 pool_timeout 抛 TimeoutError。
    # 20 + 40 = 60 条上限，覆盖 FastAPI 默认 40 的线程池。
    pool_size=20,
    max_overflow=40,
    pool_timeout=30,
    pool_pre_ping=True,
    pool_recycle=1800,
)


if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _record):  # pragma: no cover - 引擎回调
        """SQLite 并发调优。

        - journal_mode=WAL：读写不互斥（默认回滚日志模式下写会阻塞所有读）
        - busy_timeout：遇到写锁时等待而非直接抛 database is locked
        - synchronous=NORMAL：WAL 下安全且显著快于 FULL
        """
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI 依赖：请求期间提供一个数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
