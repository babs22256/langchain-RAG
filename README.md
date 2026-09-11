# RAG 电商知识库问答系统

基于 **LangChain** 框架开发的企业级 RAG（检索增强生成）知识库问答系统，面向电商商品场景。
用户通过浏览器进行知识库问答，管理员进行知识库管理。

## 功能特性

| 需求 | 实现 |
|---|---|
| 浏览器知识库管理 | 管理员上传 PDF/DOCX/TXT/MD，自动解析、分块、向量化入库，支持列表/预览/删除/统计 |
| 知识库问答 + 引用展示 | 回答标注 `[1][2]`，右侧展示命中片段（来源文件 + 相似度分） |
| 多用户多会话 | 每个用户独立会话，可新建/切换/删除 |
| 会话持久化 | 消息落 SQLite，重登恢复历史对话 |
| 注册/登录/修改密码 | JWT 认证 + bcrypt 密码哈希 |
| 权限控制 | 管理员 `admin/123456`（启动自动创建），普通用户无权访问知识库管理 |
| 企业级性能优化 | 混合检索（向量+BM25+RRF）、Reranker 重排、SSE 流式输出、结果缓存、异步、耗时统计 |

## 技术栈

- **大模型**：DeepSeek `deepseek-chat`（OpenAI 兼容）
- **Embedding / Reranker**：硅基流动 SiliconFlow `BGE-M3` / `BGE-reranker-v2-m3`
- **编排框架**：LangChain（`langchain-openai` / `langchain-text-splitters`）
- **向量存储**：numpy 余弦相似度检索（纯 Python，内嵌免 Docker，稳定可靠）
- **后端**：Python 3.11 + FastAPI + SQLAlchemy + SQLite
- **前端**：Vue3 + Vite + Element Plus + Pinia

## 目录结构

```
langchainRAG/
├─ backend/          # FastAPI 后端
│  ├─ app/
│  │  ├─ main.py     # 入口
│  │  ├─ config.py   # 配置（读 .env）
│  │  ├─ database.py # SQLAlchemy + SQLite
│  │  ├─ models/     # ORM 模型
│  │  ├─ schemas/    # Pydantic 模型
│  │  ├─ core/       # 安全与依赖注入
│  │  ├─ routers/    # auth / kb / chat / session
│  │  └─ services/   # llm / vector_store / bm25 / ingestion / retriever / rag_chain / cache
│  ├─ requirements.txt
│  └─ .env.example
├─ frontend/         # Vue3 前端
├─ sample_data/      # 样例商品知识库（手机 / 家电）
└─ README.md
```

## 快速开始

### 1. 准备 API Key

需要两个 Key：

- **DeepSeek**：https://platform.deepseek.com 注册获取（大模型）
- **硅基流动 SiliconFlow**：https://siliconflow.cn 注册获取（Embedding + 重排，免费额度足够演示）

### 2. 启动后端

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
source venv/bin/activate

pip install -r requirements.txt

# 复制并填写配置
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY 和 SILICONFLOW_API_KEY

uvicorn app.main:app --reload --port 8000
```

后端启动后：
- 接口文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health
- 向量存储随进程内嵌启动，**无需 Docker**

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173

### 4. 演示流程

1. 用 `admin / 123456` 登录 → 进入「知识库管理」→ 上传 `sample_data/` 下的样例文件。
2. 注册普通用户并登录 → 进入「知识库问答」。
3. 提问示例：「星耀 X1 Pro 的电池容量是多少？」「云净 X800 空调适合多大房间？」
4. 观察：回答中标注 `[1][2]`，下方展示引用片段与相似度；回答逐字流式输出；底部显示检索/生成耗时。
5. 退出重登，确认历史会话仍在；普通用户访问知识库管理接口返回 403。

## 核心检索流程

```
用户提问
  → 向量检索（numpy 余弦相似度，top-40）
  → BM25 关键词检索（jieba 分词，top-40）
  → RRF 融合 → top-30
  → BGE-reranker 重排 → top-5
  → 组装 Prompt（含历史对话）
  → DeepSeek 流式生成（SSE）
```

## 注意事项

- 向量检索采用纯 Python + numpy 实现（原 Milvus Lite / Chroma 在 Anaconda 环境会因原生 C++ 库冲突而段错误）；`vector_store.py` 保留统一接口，日后可无缝替换为 Milvus 等专业向量库。
- 云端 API 依赖网络，答辩前请确认两个 Key 可用、网络通畅。
- 删除文档会同步删除其向量与分块，避免"幽灵引用"。
