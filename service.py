from datetime import datetime
import threading
from persona import PERSONA
from llm import chat, chat_stream
import memory
import extractor
import vector_store
import emotion


def generate_opening():
    """生成开场白（首次打开时用）"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    prompt = [
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
    return chat(prompt, max_tokens=100)


def _build_messages(user_input, recent_messages, gap):
    """检索记忆 + 拼 system prompt，返回给 LLM 的完整消息列表"""
    related_contents = vector_store.search_memories(user_input, limit=5)
    all_memories = memory.load_memories(limit=50)
    related = [m for m in all_memories if m["content"] in related_contents]

    for m in related:
        memory.touch_memory(m["id"])

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    now_line = f"\n\n当前时间：{now}"
    if gap:
        now_line += f"\n距上次和 JoJo 聊天：{gap}"

    system_content = PERSONA + now_line

    # 注入情绪状态
    emotion_state = emotion.get_state()
    state_name = emotion_state["state"]
    state_desc = emotion.STATES[state_name]["desc"]
    system_content += f"\n\n你现在的情绪状态：{state_name}（{state_desc}）"
    system_content += "\n请在回复中自然体现这个情绪，不要直接说出状态名。"

    if related:
        memory_lines = "\n".join([f"- [{m['type']}] {m['content']}" for m in related])
        system_content += (
            f"\n\n你记得关于 JoJo 的这些事：\n{memory_lines}\n\n"
            "在合适的时候自然地用上这些记忆，不要生硬地复述。"
        )

    llm_messages = [{"role": "system", "content": system_content}]
    llm_messages += recent_messages
    return llm_messages


def stream_reply(user_input, recent_messages, max_tokens=500):
    """流式生成回复（生成器）。无副作用，保存逻辑在 app.py"""
    # 先根据用户输入更新情绪状态
    new_state, intensity, reason = emotion.decide_next_state(user_input)
    emotion.set_state(new_state, intensity, reason)

    gap = memory.last_session_gap()
    messages = _build_messages(user_input, recent_messages, gap)
    yield from chat_stream(messages, max_tokens=max_tokens)
def save_user_message(content):
    memory.save_message("user", content)


def save_assistant_message(content):
    memory.save_message("assistant", content)


def spawn_extract(user_input, assistant_reply):
    """后台线程抽取记忆，不阻塞主流程"""
    def _run(u, r):
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

    threading.Thread(target=_run, args=(user_input, assistant_reply), daemon=True).start()