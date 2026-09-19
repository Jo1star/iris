"""Iris 业务逻辑层：把 UI/接口层和底层模块隔开"""
import time
import json
import threading
from datetime import datetime

from persona import PERSONA
from llm import chat, chat_stream, chat_with_tools
import memory
import extractor
import vector_store
import emotion
import agent_tools


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
    if related:
        memory_lines = "\n".join([f"- [{m['type']}] {m['content']}" for m in related])
        system_content += (
            f"\n\n你记得关于 JoJo 的这些事：\n{memory_lines}\n\n"
            "在合适的时候自然地用上这些记忆，不要生硬地复述。"
        )

    llm_messages = [{"role": "system", "content": system_content}]
    llm_messages += recent_messages
    return llm_messages


def _get_tool_callbacks():
    """从 agent_core 拿工具回调（延迟加载，避免循环 import）"""
    from agent_core import (
        _set_intent, _clear_intent, _set_focus,
        _adjust_persona, add_reminder,
    )
    return {
        "set_wakeup_fn": add_reminder,
        "set_intent_fn": _set_intent,
        "clear_intent_fn": _clear_intent,
        "set_focus_fn": _set_focus,
        "adjust_persona_fn": _adjust_persona,
    }

def stream_reply(user_input, recent_messages, max_tokens=500):
    """流式生成回复，支持工具调用（两段式）"""
    # 1. 更新情绪
    try:
        new_state, intensity, reason = emotion.decide_next_state(user_input)
        emotion.set_state(new_state, intensity, reason)
    except Exception as e:
        print(f"[emotion] 更新失败：{e}")

    # 2. 拼消息
    gap = memory.last_session_gap()
    messages = _build_messages(user_input, recent_messages, gap)

    # 3. 拿工具回调
    try:
        callbacks = _get_tool_callbacks()
    except Exception as e:
        print(f"[stream_reply] 工具回调加载失败：{e}")
        callbacks = {}

    # 4. 工具调用循环（最多 5 轮）
    for _ in range(5):
        msg = chat_with_tools(messages, agent_tools.TOOLS_SCHEMA, max_tokens=max_tokens)

        if not msg.tool_calls:
            # 不需要工具 → 模拟流式输出
            content = msg.content or ""
            chunk_size = 4
            for i in range(0, len(content), chunk_size):
                yield content[i:i + chunk_size]
                time.sleep(0.04)
            return

        # 有工具调用 → 执行
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                } for tc in msg.tool_calls
            ]
        })

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            print(f"[chat tool] {tc.function.name}({args})")
            result = agent_tools.execute_tool(tc.function.name, args, **callbacks)
            print(f"    → {result}")
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": str(result),
            })

    yield "（我想了好久也没想清楚，要不换个话题？）"


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