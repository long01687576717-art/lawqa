# -*- coding: utf-8 -*-
"""BYOK 测试：模拟带 X-API-Key 请求头访问 /api/chat。

用法：python scripts/test_byok.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import config
from app import app
from fastapi.testclient import TestClient

client = TestClient(app)

# 从本地 .env 取一个真实 key，当作「用户自己提供的 key」
user_key = config.DEEPSEEK_API_KEY
if not user_key:
    print("未找到 API key（.env 或系统环境变量），无法测试，请先配置")
    sys.exit(1)

# 隔离测试：临时清空 .env 兜底，验证 key 只能来自请求头
config.DEEPSEEK_API_KEY = ""

# 1. 不带 X-API-Key → 应 401
r1 = client.post("/api/chat", json={"question": "试用期多久", "top_k": 3})
print(f"[1] 无 X-API-Key 请求头 -> {r1.status_code} {r1.json()}")
assert r1.status_code == 401, "预期无 key 时返回 401"

# 2. 带 X-API-Key（用户自己的 key）→ 应 200 且有回答
r2 = client.post(
    "/api/chat",
    json={"question": "没签合同赔钱", "top_k": 5},
    headers={"X-API-Key": user_key},
)
print(f"[2] 带 X-API-Key 请求头 -> {r2.status_code}")
assert r2.status_code == 200, f"预期 200，实际 {r2.status_code}：{r2.text[:200]}"
d = r2.json()
assert d.get("answer"), "回答不能为空"
print("    改写词:", d.get("rewritten_query", ""))
print("    命中法条:", "；".join("第" + l["article"] + "条" for l in d.get("laws", [])))
print("    回答前 60 字:", d["answer"][:60])

print("\n✅ BYOK 测试通过：用户自带 key 可正常调用 DeepSeek")
