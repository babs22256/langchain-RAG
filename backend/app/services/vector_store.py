"""向量存储封装（纯 Python + numpy 实现，稳定可靠）。

> 背景：原方案选用 Milvus Lite / Chroma，但它们依赖的原生 C++ 索引库（faiss/hnswlib）
> 在这台 Anaconda + Windows 环境上会触发段错误（segfault）。为保证答辩演示稳定，
> 这里改用 numpy 实现余弦相似度检索 —— 对知识库数千条分块规模完全够用。
> 本模块对外暴露统一接口，后续可无缝替换为 Milvus / Chroma 等专业向量库。
"""
import json
import os
import threading

import numpy as np

from ..config import settings


class VectorStoreService:
    _instance = None

    @classmethod
    def get_instance(cls) -> "VectorStoreService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._lock = threading.Lock()
        self._vectors = None  # np.ndarray, shape [N, dim] float32
        self._texts: list[str] = []
        self._doc_ids: list[int] = []
        self._chunk_indexes: list[int] = []
        self._load()

    def _vec_path(self) -> str:
        return f"{settings.VECTOR_STORE_PATH}.npy"

    def _meta_path(self) -> str:
        return f"{settings.VECTOR_STORE_PATH}.json"

    def _load(self) -> None:
        if os.path.exists(self._vec_path()):
            try:
                self._vectors = np.load(self._vec_path())
                with open(self._meta_path(), "r", encoding="utf-8") as f:
                    meta = json.load(f)
                self._texts = meta["texts"]
                self._doc_ids = meta["doc_ids"]
                self._chunk_indexes = meta["chunk_indexes"]
            except Exception:
                self._vectors = None

    def _save(self) -> None:
        if self._vectors is not None and len(self._vectors) > 0:
            np.save(self._vec_path(), self._vectors)
        elif os.path.exists(self._vec_path()):
            os.remove(self._vec_path())
        with open(self._meta_path(), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "texts": self._texts,
                    "doc_ids": self._doc_ids,
                    "chunk_indexes": self._chunk_indexes,
                },
                f,
                ensure_ascii=False,
            )

    def add(
        self,
        vectors: list[list[float]],
        texts: list[str],
        doc_ids: list[int],
        chunk_indexes: list[int],
    ) -> None:
        if not vectors:
            return
        with self._lock:
            arr = np.asarray(vectors, dtype=np.float32)
            self._vectors = arr if self._vectors is None else np.vstack([self._vectors, arr])
            self._texts.extend(texts)
            self._doc_ids.extend(int(d) for d in doc_ids)
            self._chunk_indexes.extend(int(i) for i in chunk_indexes)
            self._save()

    def search(self, query_vector: list[float], top_k: int = 40) -> list[dict]:
        with self._lock:
            if self._vectors is None or len(self._vectors) == 0:
                return []
            q = np.asarray(query_vector, dtype=np.float32)
            q = q / (np.linalg.norm(q) + 1e-9)
            norms = np.linalg.norm(self._vectors, axis=1, keepdims=True) + 1e-9
            scores = (self._vectors / norms) @ q  # 余弦相似度
            k = min(top_k, len(scores))
            idx = np.argsort(-scores)[:k]
            return [
                {
                    "text": self._texts[i],
                    "doc_id": self._doc_ids[i],
                    "chunk_index": self._chunk_indexes[i],
                    "score": round(float(scores[i]), 4),
                }
                for i in idx
            ]

    def delete_by_doc(self, doc_id: int) -> None:
        with self._lock:
            keep = [i for i, d in enumerate(self._doc_ids) if d != int(doc_id)]
            if self._vectors is not None:
                self._vectors = self._vectors[keep] if keep else None
            self._texts = [self._texts[i] for i in keep]
            self._doc_ids = [self._doc_ids[i] for i in keep]
            self._chunk_indexes = [self._chunk_indexes[i] for i in keep]
            self._save()

    def count(self) -> int:
        return 0 if self._vectors is None else len(self._vectors)
