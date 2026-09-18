import streamlit as st
from persona import PERSONA
import memory
import diary
import service
import emotion

st.set_page_config(page_title="Iris", page_icon="🌸")
st.title("Iris")

IRIS_AVATAR = "iris.png"
USER_AVATAR = "jojo.png"

memory.init_db()
memory.apply_time_decay()
emotion.init_emotion_table()

with st.sidebar:
    st.write(f"对话条数：{memory.count_messages()}")
    st.write(f"记忆条数：{memory.count_memories()}")
    st.write(f"归档记忆：{memory.count_archived()}")
    emo = emotion.get_state()
    st.write(f"当前情绪：{emo['state']}（{emo['intensity']:.2f}）")
    with st.expander("查看情绪历史"):
        conn = emotion.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT state, intensity, reason, created_at FROM emotion_log ORDER BY id DESC LIMIT 20")
        rows = cursor.fetchall()
        conn.close()
        for r in rows:
            st.write(f"[{r['created_at'][:16]}] {r['state']}（{r['intensity']:.2f}）— {r['reason']}")
    if st.button("清空对话"):
        memory.clear_all()
        st.session_state.messages = []
        st.rerun()
    if st.button("清空记忆"):
        memory.clear_memories()
        st.rerun()
    if st.button("让 Iris 写今天的日记"):
        with st.spinner("Iris 正在写..."):
            result = diary.write_diary()
        st.success(result)

    with st.expander("查看记忆"):
        for m in memory.load_memories(limit=20):
            st.write(f"[{m['type']}] {m['content']} ({m['importance']:.2f})")

if "messages" not in st.session_state:
    history = memory.load_recent_messages(limit=30)
    st.session_state.messages = history

    if len(history) == 0:
        first_reply = service.generate_opening()
        st.session_state.messages.append({"role": "assistant", "content": first_reply})
        memory.save_message("assistant", first_reply)

for msg in st.session_state.messages:
    avatar = IRIS_AVATAR if msg["role"] == "assistant" else USER_AVATAR
    with st.chat_message(msg["role"], avatar=avatar):
        st.write(msg["content"])

user_input = st.chat_input("和 Iris 说点什么...")

if user_input:
    service.save_user_message(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar=USER_AVATAR):
        st.write(user_input)

    with st.chat_message("assistant", avatar=IRIS_AVATAR):
        reply = st.write_stream(
            service.stream_reply(user_input, st.session_state.messages[-20:], max_tokens=500)
        )

    service.save_assistant_message(reply)
    st.session_state.messages.append({"role": "assistant", "content": reply})
    service.spawn_extract(user_input, reply)