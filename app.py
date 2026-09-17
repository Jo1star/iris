import streamlit as st
from datetime import datetime
from persona import PERSONA
from llm import chat
import memory
import extractor

st.set_page_config(page_title="Iris", page_icon="🌸")
st.title("Iris")

IRIS_AVATAR = "iris.png"
USER_AVATAR = "jojo.png"

# 初始化数据库
memory.init_db()

# 侧边栏：显示记忆条数 + 清空按钮
with st.sidebar:
    st.write(f"对话条数：{memory.count_messages()}")
    st.write(f"记忆条数：{memory.count_memories()}")
    if st.button("清空对话"):
        memory.clear_all()
        st.session_state.messages = []
        st.rerun()
    if st.button("清空记忆"):
        memory.clear_memories()
        st.rerun()

    with st.expander("查看记忆"):
        for m in memory.load_memories(limit=20):
            st.write(f"[{m['type']}] {m['content']} ({m['importance']})")

# 初始化会话状态
if "messages" not in st.session_state:
    # 从数据库读取历史
    history = memory.load_recent_messages(limit=50)
    st.session_state.messages = history

    # 如果没有历史，让 Iris 主动开口
    if len(history) == 0:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        opening_prompt = [
            {"role": "system", "content": PERSONA},
            {
                "role": "user",
                "content": (
                    f"现在是 {now}。JoJo 第一次打开对话窗口。"
                    "请你作为 Iris，主动说一句开场白。"
                    "只输出这一句话，不要加任何解释。"
                )
            }
        ]
        first_reply = chat(opening_prompt)
        st.session_state.messages.append(
            {"role": "assistant", "content": first_reply}
        )
        memory.save_message("assistant", first_reply)

# 渲染历史消息
for msg in st.session_state.messages:
    avatar = IRIS_AVATAR if msg["role"] == "assistant" else USER_AVATAR
    with st.chat_message(msg["role"], avatar=avatar):
        st.write(msg["content"])

# 输入框
user_input = st.chat_input("和 Iris 说点什么...")

if user_input:
    # 显示并保存用户消息
    st.session_state.messages.append({"role": "user", "content": user_input})
    memory.save_message("user", user_input)
    with st.chat_message("user", avatar=USER_AVATAR):
        st.write(user_input)

    # 构造发送给 LLM 的消息
    llm_messages = [{"role": "system", "content": PERSONA}]
    llm_messages += st.session_state.messages

    # 获取回复
    reply = chat(llm_messages)

    # 显示并保存 Iris 回复
    st.session_state.messages.append({"role": "assistant", "content": reply})
    memory.save_message("assistant", reply)
    with st.chat_message("assistant", avatar=IRIS_AVATAR):
        st.write(reply)

    # 抽取记忆
    extracted = extractor.extract(user_input, reply)
    for m in extracted:
        memory.save_memory(
            mem_type=m.get("type", "fact"),
            content=m.get("content", ""),
            importance=float(m.get("importance", 0.5))
        )