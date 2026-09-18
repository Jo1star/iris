import streamlit as st
from datetime import datetime
import threading
from persona import PERSONA
from llm import chat, chat_stream
import memory
import extractor
import vector_store
import diary

st.set_page_config(page_title="Iris", page_icon="🌸")
st.title("Iris")

IRIS_AVATAR = "iris.png"
USER_AVATAR = "jojo.png"

memory.init_db()
memory.apply_time_decay()

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
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        opening_prompt = [
            {"role": "system", "content": PERSONA},
            {
                "role": "user",
                "content": (
                    f"现在是 {now}。JoJo 第一次打开对话窗口。"
                    "请你作为 Iris，主动说一句开场白，不超过30个字。"
                    "只输出这一句话，不要加任何解释。"
                )
            }
        ]
        first_reply = chat(opening_prompt, max_tokens=100)
        st.session_state.messages.append(
            {"role": "assistant", "content": first_reply}
        )
        memory.save_message("assistant", first_reply)

for msg in st.session_state.messages:
    avatar = IRIS_AVATAR if msg["role"] == "assistant" else USER_AVATAR
    with st.chat_message(msg["role"], avatar=avatar):
        st.write(msg["content"])

user_input = st.chat_input("和 Iris 说点什么...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    memory.save_message("user", user_input)
    with st.chat_message("user", avatar=USER_AVATAR):
        st.write(user_input)

    # 向量检索
    related_contents = vector_store.search_memories(user_input, limit=5)
    all_memories = memory.load_memories(limit=50)
    related = [m for m in all_memories if m["content"] in related_contents]

    for m in related:
        memory.touch_memory(m["id"])

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    now_line = f"\n\n当前时间：{now}"
    gap = memory.last_session_gap()
    if gap:
        now_line += f"\n距上次和 JoJo 聊天：{gap}"

    system_content = PERSONA + now_line
    if related:
        memory_lines = "\n".join(
            [f"- [{m['type']}] {m['content']}" for m in related]
        )
        system_content += (
            f"\n\n你记得关于 JoJo 的这些事：\n{memory_lines}\n\n"
            "在合适的时候自然地用上这些记忆，不要生硬地复述。"
        )

    # 只取最近 20 条对话，减少 token
    recent_messages = st.session_state.messages[-20:]
    llm_messages = [{"role": "system", "content": system_content}]
    llm_messages += recent_messages

    # 流式输出
    with st.chat_message("assistant", avatar=IRIS_AVATAR):
        reply = st.write_stream(chat_stream(llm_messages, max_tokens=500))

    st.session_state.messages.append({"role": "assistant", "content": reply})
    memory.save_message("assistant", reply)

    # 后台异步抽取记忆
    def _extract_and_save(u, r):
        try:
            extracted = extractor.extract(u, r)
            for m in extracted:
                memory.save_memory(
                    mem_type=m.get("type", "fact"),
                    content=m.get("content", ""),
                    importance=float(m.get("importance", 0.5))
                )
        except Exception as e:
            print(f"[extract error] {e}")

    threading.Thread(
        target=_extract_and_save,
        args=(user_input, reply),
        daemon=True
    ).start()