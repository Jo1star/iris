# Iris

陪伴型长期记忆情绪 Agent。

## 简介

Iris 是一个带有长期记忆和情绪状态机的陪伴型 AI。
目标：记得住、情绪有变化、人格稳定、关系连续。

项目核心不是"聊天"，而是**能记住、能想起来、能长期运行**。

## 当前进度

- [x] 环境搭建（Python 3.11 + venv）
- [x] 接入 DeepSeek API
- [x] Git + GitHub + SSH
- [x] Streamlit 界面 + 多轮对话
- [x] 头像：iris.png / jojo.png
- [x] 人格圣经 v0.1
- [x] SQLite 持久化对话历史
- [x] 记忆抽取，存入 memories 表
- [x] 向量检索（ChromaDB + 多语言嵌入模型）
- [x] 内网穿透，移动端可访问
- [ ] 记忆衰减与清理
- [ ] 冲突消解
- [ ] 情绪状态机
- [ ] 语音（STT + TTS）
- [ ] React 网页版

## 架构
用户（浏览器/手机）
↓
Streamlit 界面层（app.py）
↓
逻辑层
├── llm.py 调 DeepSeek
├── extractor.py 抽取结构化记忆
└── vector_store.py 向量检索
↓
存储层
├── SQLite：messages + memories
└── ChromaDB：记忆向量

## 核心数据流
用户输入
↓
保存到 messages 表
↓
向量检索相关记忆（memories）
↓
拼进 system prompt
↓
调 DeepSeek 生成回复
↓
保存回复到 messages 表
↓
抽取新记忆 → 过滤 → 去重 → 双写 SQLite + 向量库


## 技术栈

- Python 3.11
- DeepSeek API
- Streamlit
- SQLite
- ChromaDB
- sentence-transformers
- Git / GitHub
- 樱花 frp（内网穿透）

## 文件说明

| 文件 | 作用 |
|------|------|
| app.py | Streamlit 主界面 |
| llm.py | DeepSeek 调用封装 |
| persona.py | 人格圣经 |
| memory.py | SQLite 读写（messages + memories） |
| extractor.py | 从对话抽取结构化记忆 |
| vector_store.py | ChromaDB 向量检索 |
| iris.db | 本地数据库（已 .gitignore） |
| chroma_db/ | 向量库持久化目录（已 .gitignore） |

## 文档

- [PROJECT_STATE.md](PROJECT_STATE.md)：项目当前进度
- [TECH_STACK.md](TECH_STACK.md)：技术栈与知识点总结

## 运行方式

安装依赖：

```bash
pip install -r requirements.txt

配置 .env：
DEEPSEEK_API_KEY=你的key

启动：
streamlit run app.py
移动端访问
通过樱花 frp 内网穿透，手机在任意网络下都能访问。
记忆统一存储在本地 SQLite，多端共享同一份数据。
