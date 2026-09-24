"""劳动法知识库问答系统 —— FastAPI 主程序。"""
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config  # noqa: F401  （确保加载 .env）
import llm
from retriever import KnowledgeBase

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="劳动法知识库问答", version="1.0.0")

# 托管前端静态文件
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 启动时构建知识库索引（法条 + 案例的向量/BM25）
print("正在构建知识库索引……")
kb = KnowledgeBase()


class ChatRequest(BaseModel):
    question: str
    top_k: int = 5


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/health")
def health():
    return {"ok": True, "laws": len(kb.laws), "cases": len(kb.cases)}


@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    q = (req.question or "").strip()
    if not q:
        return JSONResponse({"error": "问题不能为空"}, status_code=400)
    if len(q) > 500:
        return JSONResponse({"error": "问题太长，请控制在 500 字以内"}, status_code=400)

    # 1. 取 API key：请求头 X-API-Key 优先，其次本地 .env（便于本地调试）
    api_key = (request.headers.get("X-API-Key") or "").strip() or config.DEEPSEEK_API_KEY
    if not api_key:
        return JSONResponse({"error": "请配置 API Key"}, status_code=401)

    # 2. 查询改写：口语化问题 -> 法律专业检索词
    try:
        rewrite = llm.rewrite_query(q, api_key)
    except Exception:
        rewrite = q  # 改写失败则退回原问题继续检索

    # 3. 用改写后的词做混合检索
    laws, cases = kb.search(rewrite, k=req.top_k)

    # 4. 用原问题 + 检索结果生成回答
    try:
        answer = llm.generate_answer(q, laws, cases, api_key)
    except Exception as e:
        return JSONResponse({"error": f"调用大模型失败：{e}"}, status_code=500)

    return {"answer": answer, "laws": laws, "cases": cases, "rewritten_query": rewrite}


if __name__ == "__main__":
    print("服务已启动：http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
