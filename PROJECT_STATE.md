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
- 时间衰减（半衰期 30 天）+ 低分归档（软删除，可恢复）
- 流式输出，回复首字从 20 秒+ 降到 1 秒内
- 主回复与记忆抽取使用独立 client，避免连接池竞争
- 模型缓存 @st.cache_resource，避免重复加载
- HF 镜像（hf-mirror.com），国内可下载 HuggingFace 模型
- Day 8：语义去重（向量相似度合并，SIM_MERGE=0.90，合并时不动向量库）
- Day 8：收紧记忆抽取评分标准，项目进度类不再入库

## 当前文件
- app.py：Streamlit 主界面，负责对话、记忆抽取、侧边栏
- llm.py：DeepSeek 调用封装，主 client + extract_client 独立
- persona.py：人格圣经
- memory.py：SQLite 读写，messages 表 + memories 表，含语义去重
- extractor.py：从对话中抽取结构化记忆，含评分量规
- vector_store.py：ChromaDB 向量检索，含 find_similar（带相似度）
- test_dedup.py：Day 8 去重测试脚本
- test_latency.py：LLM 首字延迟测试脚本
- .env：API Key
- .gitignore
- requirements.txt
- iris.png / jojo.png
- PROJECT_STATE.md
- README.md
- TECH_STACK.md
- iris.db：本地数据库，已被 .gitignore 忽略
- chroma_db/：向量库，已被 .gitignore 忽略

## 数据库结构
messages(id, role, content, created_at)
memories(id, type, content, importance, created_at, last_accessed, archived)

## 语义去重规则（Day 8）
- 新记忆入库前，先查向量库最相似的一条
- 相似度 > 0.90：合并到旧记忆（取 max importance，刷新 last_accessed）
- 相似度 0.70 ~ 0.90：新增，但打印 [dedup 灰区] 日志观察
- 相似度 < 0.70：正常新增
- 合并时不动向量库文档，避免 SQLite/Chroma 内容不一致

## 下一步
Day 9：冲突消解
- 检测新旧记忆矛盾（如"喜欢画画" vs "不再喜欢画画"）
- 策略：新覆盖旧 / 保留时间线 / 询问用户
- 需要先攒几天的 [dedup 灰区] 日志观察数据

Day 10：离线评估
- 构造测试集
- 测记忆召回率、准确率
- 消融实验：去掉向量检索，指标掉多少

Day 11：情绪状态机
- 定义 5-8 个情绪状态
- 状态转移规则 + 衰减
- 情绪影响回复语气

后续
- 语音（STT + TTS）
- React 网页版
- 部署到云服务器

## 人格设定
- 称呼用户：JoJo
- 性格：温柔细腻，偶尔活泼俏皮，有小脾气
- 核心欲望：想一直陪着 JoJo

## 已知问题
- PyCharm 2020.1.1 显示 Python 3.1，实际是 3.11，不影响运行
- Python Console 报 TypeError，不用管
- Database 面板连接卡住，不用管
- Streamlit 运行时终端被占用，敲 git 命令请新开终端
- DeepSeek 网络高峰期首字延迟可达 4-5 秒，属服务端波动，非代码问题
- 语义去重的 0.90 阈值是保守值，实际效果需要聊几天看灰区日志再调

## 沟通约定
- 每次新对话，先发这个文件内容
- 每完成一个 Day，更新此文件并 push
- 遇到延迟类问题，先跑 test_latency.py 隔离，确认是服务端再动代码