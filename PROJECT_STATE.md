# Iris 项目状态

## 当前版本
Iris 0.1

## 已完成
- Python 3.11 + 虚拟环境
- DeepSeek API 调用
- Streamlit 界面 + 多轮对话
- 头像：iris.png / jojo.png
- 人格圣经 v0.1
- Git + GitHub + SSH
- SQLite 持久化对话历史
- 记忆抽取，存入 memories 表
- 通过樱花 frp 内网穿透，实现移动端公网访问，记忆统一存储于本地 SQLite
- 向量检索（ChromaDB + 多语言嵌入模型），记忆能语义召回
## 当前文件
- app.py：Streamlit 主界面，负责对话、记忆抽取、侧边栏
- llm.py：DeepSeek 调用封装
- persona.py：人格圣经
- memory.py：SQLite 读写，messages 表 + memories 表
- extractor.py：从对话中抽取结构化记忆
- main.py：早期测试文件
- .env：API Key
- .gitignore
- requirements.txt
- iris.png / jojo.png
- PROJECT_STATE.md
- README.md
- iris.db：本地数据库，已被 .gitignore 忽略

## 数据库结构
messages(id, role, content, created_at)
memories(id, type, content, importance, created_at)

## 下一步
Day 6：检索记忆，拼进 prompt
- 让 Iris 根据用户当前输入，检索相关记忆
- 把记忆拼进 system 或上下文
- 测试：用户问“我喜欢什么颜色”，她能答“墨绿色”

Day 7：记忆衰减与清理（时间衰减、低分归档、去重加强）
## 人格设定
- 称呼用户：JoJo
- 性格：温柔细腻，偶尔活泼俏皮，有小脾气
- 核心欲望：想一直陪着 JoJo

## 已知问题
- PyCharm 2020.1.1 显示 Python 3.1，实际是 3.11，不影响运行
- Python Console 报 TypeError，不用管
- Database 面板连接卡住，不用管
- Git 已配 SSH，推送正常
- Streamlit 运行时终端被占用，敲 git 命令请新开终端

## 沟通约定
- 每次新对话，先发这个文件内容
- 每完成一个 Day，更新此文件并 push

