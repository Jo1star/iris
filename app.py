import streamlit as st
from datetime import datetime
from persona import PERSONA
from llm import chat

st.set_page_config(page_title="Iris", page_icon="💙")
IRIS_AVATAR = "iris.png"
USER_AVATAR = "jojo.png"
st.title("Iris")

# 初始化会话状态
if "messages" not in st.session_state:
    st.session_state.messages = []

    # 让 Iris 自己开口说第一句
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    opening_prompt = [
        {"role": "system", "content": PERSONA},
        {
            "role": "user",
            "content": (
                f"现在是 {now}。JoJo 刚刚打开对话窗口。"
                "请你作为 Iris，主动说一句开场白。"
                "只输出这一句话，不要加任何解释。"
            )
        }
    ]
    first_reply = chat(opening_prompt)
    st.session_state.messages.append(
        {"role": "assistant", "content": first_reply}
    )

# 渲染历史消息
for msg in st.session_state.messages:
    avatar = IRIS_AVATAR if msg["role"] == "assistant" else USER_AVATAR
    with st.chat_message(msg["role"], avatar=avatar):
        st.write(msg["content"])

# 输入框
user_input = st.chat_input("和 Iris 说点什么...")

if user_input:
    # 显示用户消息
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user",avatar=USER_AVATAR):
        st.write(user_input)

    # 构造发送给 LLM 的消息
    llm_messages = [{"role": "system", "content": PERSONA}]
    llm_messages += st.session_state.messages

    # 获取回复
    reply = chat(llm_messages)

    # 显示 Iris 回复
    st.session_state.messages.append({"role": "assistant", "content": reply})
    with st.chat_message("assistant",avatar=IRIS_AVATAR):
        st.write(reply)