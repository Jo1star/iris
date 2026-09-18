"""
Iris Agent Core —— 常驻进程，独立于 Streamlit 跑。
启动方式：python agent_core.py
停止方式：Ctrl + C
"""
import time
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).parent / "iris.db"

DEFAULT_WAKEUP_MINUTES = 5  # 第一次如果没有状态，默认 5 分钟后再醒


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_agent_tables():
    """建两张表：agent_state（存下次唤醒时间）、agent_messages（存她主动说的话）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            next_wakeup_at TEXT NOT NULL,
            last_wakeup_at TEXT,
            wakeup_reason TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            intent TEXT,
            created_at TEXT NOT NULL,
            delivered INTEGER DEFAULT 0,
            delivered_at TEXT
        )
    """)
    cursor.execute("SELECT COUNT(*) as c FROM agent_state")
    if cursor.fetchone()["c"] == 0:
        next_wakeup = datetime.now() + timedelta(minutes=DEFAULT_WAKEUP_MINUTES)
        cursor.execute(
            "INSERT INTO agent_state (id, next_wakeup_at, wakeup_reason) VALUES (1, ?, ?)",
            (next_wakeup.isoformat(), "首次启动")
        )
    conn.commit()
    conn.close()


def get_agent_state():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT next_wakeup_at, last_wakeup_at, wakeup_reason FROM agent_state WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def set_next_wakeup(minutes, reason=""):
    """设置下次唤醒时间"""
    next_wakeup = datetime.now() + timedelta(minutes=minutes)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE agent_state SET next_wakeup_at=?, wakeup_reason=? WHERE id=1",
        (next_wakeup.isoformat(), reason)
    )
    conn.commit()
    conn.close()
    return next_wakeup


def mark_woke_up():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE agent_state SET last_wakeup_at=? WHERE id=1",
        (datetime.now().isoformat(),)
    )
    conn.commit()
    conn.close()


def wakeup_and_decide():
    """醒来后：让 LLM 决策 + 调用工具 + 决定说什么/何时再醒"""
    from persona import PERSONA
    from llm import chat_with_tools
    import agent_tools
    import memory

    # 收集上下文
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M %A")
    gap = memory.last_session_gap(threshold_minutes=60)

    # 拼 system prompt
    system_prompt = PERSONA + f"""

现在你醒来了。现在是 {now_str}。
{f"距上次和 JoJo 对话：{gap}" if gap else "JoJo 刚才还在和你说话。"}

你可以：
- 用工具查时间、天气、回忆
- 决定要不要主动对 JoJo 说一句话
- 决定自己下次什么时候醒来

规则：
- 如果现在是深夜（23:00-07:00），除非有特殊理由，不要主动说话，直接设置下次醒来在早上。
- 如果距上次对话很短（<1 小时），一般不要打扰。
- 如果你决定说话，说一句自然的话，20-50 字。
- 无论说不说话，都必须调用 set_wakeup 决定下次什么时候醒。
"""

    messages = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "user", "content": "你醒了。请决策。"})

    # 决策循环（最多 5 轮，防止死循环）
    for _ in range(5):
        msg = chat_with_tools(messages, agent_tools.TOOLS_SCHEMA, max_tokens=300)

        # 没有工具调用 → LLM 想说话
        if not msg.tool_calls:
            content = msg.content or ""
            if content.strip():
                save_agent_message(content, intent="主动")
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Iris 说：{content}")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Iris 选择沉默")
            return

        # 有工具调用 → 执行，把结果喂回去
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                } for tc in msg.tool_calls
            ]
        })

        for tc in msg.tool_calls:
            import json
            args = json.loads(tc.function.arguments or "{}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 调用工具：{tc.function.name}({args})")
            result = agent_tools.execute_tool(
                tc.function.name, args,
                set_wakeup_fn=lambda m, r: set_next_wakeup(m, r)
            )
            print(f"    → {result}")
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": str(result)
            })


def save_agent_message(content, intent=""):
    """把 Iris 主动说的话写进 agent_messages 表"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO agent_messages (content, intent, created_at) VALUES (?, ?, ?)",
        (content, intent, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def main_loop():
    """主循环：睡 → 醒 → 决策 → 再睡"""
    print("=" * 50)
    print("Iris Agent Core 启动")
    print(f"数据库：{DB_PATH}")
    print("Ctrl + C 停止")
    print("=" * 50)

    init_agent_tables()

    while True:
        state = get_agent_state()
        next_wakeup = datetime.fromisoformat(state["next_wakeup_at"])
        now = datetime.now()

        if now >= next_wakeup:
            mark_woke_up()
            try:
                wakeup_and_decide()
            except Exception as e:
                print(f"[错误] 决策失败：{e}")
                set_next_wakeup(5, "出错后重试")
        else:
            seconds_left = (next_wakeup - now).total_seconds()
            print(f"下次唤醒：{next_wakeup.strftime('%H:%M:%S')}（还有 {int(seconds_left)} 秒）")
            # 睡 30 秒检查一次，不占 CPU
            time.sleep(min(30, seconds_left))


if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\nAgent Core 已停止")