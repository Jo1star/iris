# Iris

陪伴型长期记忆 + 情绪状态机的 AI。

目标：记得住、情绪有变化、人格稳定、关系连续。

项目核心不是"聊天"，而是**能记住、能想起来、能长期运行**——她不只在等你说话，没人时也会自己醒来想事、写日记，还会进 Minecraft 自己找事做。

## 当前形态

- 后端：FastAPI（`server.py`），单进程同时跑 Web 服务和常驻 Agent 循环
- 前端：单页 `web/index.html`（原生 JS，无构建步骤）
- 常驻：`agent_core.py` 事件驱动循环，由 `server.py` 后台线程拉起
- 外部：Minecraft 桥接（`mc_bridge.py` + `iris-mc/control/bot.js`）
- 模型：DeepSeek（主回复与记忆抽取使用两个独立 client，避免连接池竞争）

## 架构

```
浏览器 / 手机
  ↓ HTTP
server.py（FastAPI，:8000）
  ├── 静态页 web/index.html
  ├── /api/chat → service.stream_reply（流式）
  └── 后台线程 → agent_core.main_loop
                        ↕ event_bus（进程内队列）
                   message / emotion / reminder / manual
  ↓
service.py（业务层）
  ├── persona.py      人格圣经
  ├── llm.py          DeepSeek 封装（chat / chat_stream / chat_with_tools）
  ├── memory.py       SQLite 读写、语义去重、时间衰减、检索
  ├── extractor.py    从对话抽取结构化记忆（带评分量规）
  ├── vector_store.py ChromaDB 向量检索
  ├── emotion.py      情绪状态机（8 状态 + 衰减 + 优先级）
  ├── agent_tools.py  她可以调用的工具
  └── diary.py        每日日记生成
  ↓
存储层
  ├── SQLite：iris.db（messages / memories / emotion_* / agent_*）
  └── ChromaDB：chroma_db/（记忆向量）
```

## 核心数据流

```
用户输入
  ↓
写入 messages
  ↓
向量检索相关记忆（ChromaDB）→ 拼进 system prompt
  ↓
DeepSeek 流式生成回复
  ↓
写入 messages → 推送 emotion 事件到 event_bus
  ↓
异步抽取新记忆 → 过滤 → 语义去重 → 双写 SQLite + 向量库
```

## 常驻循环（agent_core）

事件驱动，不再定时轮询：

```
等事件或超时（取 下次唤醒 与 待办到期 的最小值）
  ↓ 醒
读内部状态（last_thought / current_focus / pending_intent）
  ↓
LLM 决策 → 调用工具（查时间、回忆、设提醒、调人格…）
  ↓
写 agent_journal（观察 / 想法 / 动作）
  ↓
设定下次唤醒 → 继续等
```

她会有"待办念头"（pending_intent），到期自己想起来。

## 数据库表

| 表 | 作用 |
|---|---|
| messages | 聊天记录 |
| memories | 结构化记忆（importance / last_accessed / archived） |
| emotion_state / emotion_log | 当前情绪 + 情绪变化历史 |
| agent_state | 下次唤醒时间 |
| agent_inner_state | 内心状态（上个念头、当前关注、待办念头） |
| agent_messages | 她主动说的话 |
| agent_journal | 每次醒来的一条记录 |

## 文件说明

| 文件 | 作用 |
|---|---|
| server.py | FastAPI 后端 + 静态页 + 拉起 Agent 线程 |
| web/index.html | 前端单页 |
| service.py | 业务逻辑层 |
| agent_core.py | 常驻 Agent 核心（事件驱动循环） |
| event_bus.py | 进程内事件总线 |
| memory.py | SQLite 读写、去重、衰减、检索 |
| extractor.py | 记忆抽取 |
| vector_store.py | ChromaDB 向量检索 |
| emotion.py | 情绪状态机 |
| agent_tools.py | 工具实现 + schema |
| diary.py | 每日日记 |
| persona.py | 人格圣经 |
| llm.py | DeepSeek 封装 |
| mc_bridge.py | Minecraft 桥接（MCP + 自主行动） |
| iris-mc/control/bot.js | mineflayer 机器人 + WebSocket |
| tests/ | 手工验证脚本（需真实环境） |

## 运行

```bash
# 依赖（Python 3.11）
pip install -r requirements.txt

# 配置 .env
DEEPSEEK_API_KEY=你的key

# 启动（Web 服务 + 常驻 Agent 一起起来）
python server.py
# → http://localhost:8000

# 只跑 Agent 核心（收不到网页事件，一般不用）
python agent_core.py
```

Minecraft 部分：先跑起本地 MC 服务端（`127.0.0.1:64008`，1.20.1），再启动 `iris-mc/control/bot.js`，最后 `python mc_bridge.py`。

## 文档

- [PROJECT_STATE.md](PROJECT_STATE.md) — 当前进度、已知问题、下一步

## 已知设计取舍

- 语义去重阈值 0.90（合并）/ 0.70（灰区观察），保守值，靠聊天积累日志再调
- 合并记忆时不动向量库文档，避免 SQLite 与 Chroma 内容不一致
- 记忆时间衰减半衰期 30 天，importance < 0.2 归档（软删除，可恢复）
