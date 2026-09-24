# 劳动法知识库问答系统

一个基于 **DeepSeek 大模型 + 本地向量检索** 的 RAG（检索增强生成）问答系统：收录中国劳动法条与劳动争议案例，用户提问后，系统检索出最相关的法条和相似案例，交给大模型生成带出处的回答。

## 功能

- 🔍 语义检索：向量检索 + 关键词检索混合，自动匹配最相关的法条与案例
- 💬 智能问答：调用 DeepSeek 生成回答，并引用具体法条与案例
- 📖 内置数据：《劳动法》107 条 +《劳动合同法》98 条（来自公开渠道，可核验）
- ⚖️ 案例库：支持自己批量导入真实案例

## 目录结构

```
lawqa/
├── app.py              # FastAPI 主程序（网页 + API）
├── retriever.py        # 检索：加载数据、向量 + BM25
├── llm.py              # 调用 DeepSeek 生成回答
├── config.py           # 读取 .env 配置
├── requirements.txt    # 依赖清单
├── .env.example        # API Key 模板
├── run.bat             # Windows 双击启动
├── static/index.html   # 聊天界面
├── scripts/
│   ├── build_laws.py   # 法条数据解析（一般不用重跑）
│   └── build_cases.py  # 案例数据解析（导入案例时用）
└── data/
    ├── laws.json       # 法条数据（已内置）
    ├── cases.json      # 案例数据（由 build_cases.py 生成）
    ├── _cases_raw/     # ★ 放案例原文的地方
    └── _raw_*.txt      # 法条原始文本（供 build_laws.py 复现用）
```

## 快速开始（Windows）

1. **申请 DeepSeek API Key**：打开 <https://platform.deepseek.com>，注册后创建 API Key（按量计费，很便宜）。

2. **配置 Key**：复制 `.env.example` 为 `.env`，把里面的 `DEEPSEEK_API_KEY=sk-xxxx` 改成你的 Key。

3. **启动**：双击 `run.bat`（首次会自动安装依赖 + 下载约 100MB 中文向量模型，耐心等待几分钟）。

4. **使用**：浏览器打开 <http://127.0.0.1:8000>，输入问题即可。

> 手动启动（不用 bat）：
> ```bash
> pip install -r requirements.txt
> python app.py
> ```

## 如何添加案例

1. 把你搜集到的案例原文，每个案例存成一个 `.txt` 文件，放进 `data/_cases_raw/` 目录。
2. 用下面格式标注字段（`【标签】` 或 `标签：` 两种写法都行）：

```text
【标题】案例名称
【案号】（2011）杭滨民初字第885号
【法院】浙江省杭州市滨江区人民法院
【关键词】劳动合同 单方解除
【案情】
这里粘贴基本案情，可多行。
【裁判要点】
这里写裁判要点，可多行。
【来源】https://www.court.gov.cn/...
```

   - 只有 `标题` 是建议必填的（缺失会用文件名兜底）；`案情`、`裁判要点`、`案号` 至少填一个。
   - 以 `_` 开头的文件会被忽略（模板文件 `_模板.txt` 即如此）。
   - 参考示例：`data/_cases_raw/指导案例18号_中兴通讯诉王鹏劳动合同纠纷案.txt`

3. 运行解析脚本：

```bash
python scripts/build_cases.py
```

   会生成/更新 `data/cases.json`。

4. **重启服务**（关掉重开 `run.bat`），即可检索到新案例。

## 数据来源说明

- 法条文本来自公开渠道（维基文库镜像，与全国人大官网文本一致），录入前已抽样核对关键条文。
- 案例请务必使用**真实、可核验**的公开案例（如最高人民法院指导性案例、人社部/最高法联合发布的典型案例、裁判文书网公开文书），不要虚构案号或案情。

## 技术栈

- 后端：Python + FastAPI + Uvicorn
- 大模型：DeepSeek（OpenAI 兼容接口，`deepseek-chat`）
- 检索：`fastembed` + `BAAI/bge-small-zh-v1.5`（ONNX，无需 PyTorch）+ `jieba` BM25 兜底
- 存储：JSON 文件，无需数据库

## 免责声明

本工具仅供学习与信息参考，**不构成法律意见**。法条与案例内容请以官方发布为准，遇到具体法律问题请咨询执业律师。
