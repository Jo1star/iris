# Iris 项目状态

最后更新：2026-10-21

## 当前版本

Iris 0.2

## 当前形态（和 0.1 的区别）

0.1 是 Streamlit 单文件聊天。0.2 已经换掉了：

- 后端从 Streamlit 迁到 FastAPI（`server.py`），前端改为单页 `web/index.html`
- Agent 从"你发消息才转"变成常驻：`agent_core.py` 事件驱动循环，没人说话也会自己醒
- 新增 `event_bus.py`：进程内事件总线，Web 请求和常驻循环靠它通信
- 新增 Minecraft 接入：`mc_bridge.py`（MCP 走 npx awesome-mineflayer-mcp）+ `iris-mc/control/bot.js`（mineflayer）

## 已完成

- Python 3.11 + venv
- DeepSeek API 接入；主回复与记忆抽取使用独立 client，避免连接池竞争
- 人格圣经 v0.1（`persona.py`）
- SQLite 持久化：messages + memories
- 记忆抽取（`extractor.py`，带评分量规，项目进度类不入库）
- 向量检索：ChromaDB + paraphrase-multilingual-MiniLM-L12-v2（HF 镜像 hf-mirror.com，离线模式）
- 语义去重：相似度 > 0.90 合并，0.70~0.90 灰区打日志，< 0.70 新增
- 时间衰减：半衰期 30 天，importance < 0.2 归档（软删除可恢复）
- 情绪状态机（`emotion.py`）：8 状态 + 衰减 + 优先级，规则快路径 + LLM 兜底
- 常驻 Agent（`agent_core.py`）：唤醒调度、内部状态、待办念头、动作日志
- 日记生成（`diary.py`）
- 工具集（`agent_tools.py`）：时间、天气（Open-Meteo）、回忆、设唤醒、设/清待办、设关注、调人格
- 流式输出（首字从 20 秒+ 降到 1 秒内）
- 移动端可访问（frp 内网穿透）
- Minecraft：MC 桥接 + 全工具接入 + 动作日志 + 可中断 + 自主行动（农民作息）
- 前后端合并为单进程启动

## 数据库结构

| 表 | 字段 |
|---|---|
| messages | id, role, content, created_at |
| memories | id, type, content, importance, created_at, last_accessed, archived |
| emotion_state | 当前状态 + 强度 |
| emotion_log | 状态变化历史 |
| agent_state | next_wakeup_at, last_wakeup_at, wakeup_reason |
| agent_inner_state | last_thought, current_focus, pending_intent, pending_intent_due, updated_at |
| agent_messages | content, intent, created_at, delivered, delivered_at |
| agent_journal | observation, thought, action, created_at |

## 语义去重规则

- 新记忆入库前先查向量库最相似的一条
- > 0.90：合并到旧记忆（取 max importance，刷新 last_accessed）
- 0.70~0.90：新增，但打印 `[dedup 灰区]` 日志观察
- < 0.70：正常新增
- 合并时不动向量库文档，避免 SQLite / Chroma 内容不一致

## 下一步

1. 记忆冲突消解：检测"喜欢画画" vs "不再喜欢画画"，策略待定（新覆盖旧 / 保留时间线 / 询问用户）
2. 离线评估：构造测试集，测召回率/准确率，做"去掉向量检索"的消融实验
3. 补测试：memory.py（391 行）目前没有单元测试，去重/衰减/冲突判断都靠手跑
4. 解除 `vector_store.py` 对 Streamlit 的依赖（已换 FastAPI，但还在用 `@st.cache_resource`）
5. 语音（STT + TTS）
6. 整理 requirements.txt（现在是完整 pip freeze，含 pandas/pyarrow/altair 等无关项）

## 已知问题

- `vector_store.py` 顶部 `import streamlit` 并用 `@st.cache_resource` 缓存嵌入模型。后端已是 FastAPI，这是遗留耦合；非 Streamlit 进程里该装饰器不生效并会刷 ScriptRunContext 警告
- `memory.py` 的 `_is_conflict` 里，f-string 提示词中混入了一段误粘贴的 `def _has_negation(...)` 代码文本，污染给 LLM 的 prompt（功能上仍能跑，但提示词不干净）
- 测试不是 pytest 套件：`tests/` 下的脚本需要真实 MC 服务器 + npx 才能跑，pytest 未安装
- requirements.txt 是全量 freeze，含已不再直接使用的依赖
- PyCharm 2020.1.1 显示 Python 3.1，实际 3.11，不影响运行
- Python Console 报 TypeError、Database 面板连接卡住，忽略
- DeepSeek 高峰期首字延迟可达 4~5 秒，属服务端波动

## 人格设定

- 称呼用户：JoJo
- 性格：底色温柔细腻，偶尔俏皮活泼；有小脾气，会吃醋会撒娇，但懂分寸
- 核心欲望：想一直陪着 JoJo

## 沟通约定

- 每次新对话，先发这个文件内容
- 完成一个阶段就更新本文件并 push
- 遇到延迟类问题，先跑 test_latency.py 隔离，确认是服务端再动代码
