"""全局配置：从 .env 读取密钥与运行参数。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- DeepSeek 大模型 ----
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # ---- 硅基流动 SiliconFlow（Embedding + 重排） ----
    SILICONFLOW_API_KEY: str = ""
    SILICONFLOW_BASE_URL: str = "https://api.siliconflow.cn/v1"
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    RERANK_MODEL: str = "BAAI/bge-reranker-v2-m3"

    # ---- 认证 ----
    SECRET_KEY: str = "please-change-me-to-a-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 天

    # ---- 数据库 ----
    DATABASE_URL: str = "sqlite:///./app.db"

    # ---- 向量存储路径（numpy 余弦相似度检索） ----
    VECTOR_STORE_PATH: str = "./vector_store"

    # ---- 管理员初始账号 ----
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "123456"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
