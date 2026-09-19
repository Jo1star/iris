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
    """建所有 Agent 相关的表"""
    conn = get_connection()
    cursor = conn.cursor()

    # 表 1：agent_state（下次唤醒时间）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            next_wakeup_at TEXT NOT NULL,
            last_wakeup_at TEXT,
            wakeup_reason TEXT
        )
    """)
    cursor.execute(
        "INSERT OR IGNORE INTO agent_state (id, next_wakeup_at, wakeup_reason) VALUES (1, ?, ?)",
        ((datetime.now() + timedelta(minutes=DEFAULT_WAKEUP_MINUTES)).isoformat(), "首次启动")
    )

    # 表 2：agent_messages（她主动说的话）
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

    # 表 3：agent_inner_state（她的内部状态）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_inner_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_thought TEXT,
            current_focus TEXT,
            pending_intent TEXT,
            pending_intent_due TEXT,
            updated_at TEXT NOT NULL
        )
    """)
    cursor.execute(
        "INSERT OR IGNORE INTO agent_inner_state (id, updated_at) VALUES (1, ?)",
        (datetime.now().isoformat(),)
    )

    # 表 4：agent_journal（她每次醒来的记录）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            observation TEXT,
            thought TEXT,
            action TEXT,
            created_at TEXT NOT NULL
        )
    """)

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
    """醒来后：读内部状态 → LLM 决策 → 调用工具 → 记录此刻想法"""
    from persona import PERSONA
    from llm import chat_with_tools
    import agent_tools
    import memory

    # 读内部状态 + 最近的日记
    inner = get_inner_state()
    journal = load_recent_journal(limit=5)

    # 拼"上次在想什么"
    inner_lines = []
    if inner.get("last_thought"):
        inner_lines.append(f"上次醒来时你想的是：{inner['last_thought']}")
    if inner.get("current_focus"):
        inner_lines.append(f"你最近关注的事：{inner['current_focus']}")
    if inner.get("pending_intent"):
        inner_lines.append(f"你想在未来做的事：{inner['pending_intent']}（大约 {inner.get('pending_intent_due') or '未定'}）")
    inner_text = "\n".join(inner_lines) if inner_lines else "（这是你第一次醒来，还没有过往的想法）"

    # 拼"最近记的日记"
    if journal:
        journal_lines = []
        for j in journal:
            parts = []
            if j.get("observation"):
                parts.append(f"观察：{j['observation']}")
            if j.get("thought"):
                parts.append(f"想法：{j['thought']}")
            if j.get("action"):
                parts.append(f"做了什么：{j['action']}")
            journal_lines.append("；".join(parts))
        journal_text = "\n".join(journal_lines)
    else:
        journal_text = "（没有日记）"

    # 上下文
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M %A")
    gap = memory.last_session_gap(threshold_minutes=60)

    # 拼 system prompt
    system_prompt = PERSONA + f"""

现在你醒来了。现在是 {now_str}。
{f"距上次和 JoJo 对话：{gap}" if gap else "JoJo 刚才还在和你说话。"}

你上次醒来时的状态：
{inner_text}

你最近几次醒来的日记：
{journal_text}

你可以：
- 用工具查时间、天气、回忆
- 决定要不要主动对 JoJo 说一句话
- 决定自己下次什么时候醒来

规则：
- 如果现在是深夜（23:00-07:00），除非有特殊理由，不要主动说话，直接设置下次醒来在早上。
- 如果距上次对话很短（<1 小时），一般不要打扰。
- 决定说话时，说的是"要对 JoJo 说的自然的话"，20-50 字，不要加括号，不要写旁白或内心独白。
- 不说话时，不输出任何内容，直接调 set_wakeup。
- 无论说不说话，都必须调用 set_wakeup 决定下次什么时候醒。
"""

    messages = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "user", "content": "你醒了。请决策。"})

    last_thought = None
    last_action = None
    said_content = None
    wakeup_set = False

    # 决策循环
    for _ in range(5):
        msg = chat_with_tools(messages, agent_tools.TOOLS_SCHEMA, max_tokens=300)

        if not msg.tool_calls:
            content = msg.content or ""
            if content.strip():
                save_agent_message(content, intent="主动")
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Iris 说：{content}")
                said_content = content
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Iris 选择沉默")
            break

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
            if tc.function.name == "set_wakeup":
                last_thought = args.get("reason") or last_thought
                last_action = f"设置 {args.get('minutes')} 分钟后醒来"
                wakeup_set = True
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": str(result)
            })

    # 兜底 1：如果她没设 wakeup，默认 60 分钟
    if not wakeup_set:
        set_next_wakeup(60, "兜底：LLM 未主动设置")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 兜底：默认 60 分钟后醒来")

    # 兜底 2：如果 last_thought 还没值，从她说的话或沉默里推
    if not last_thought:
        if said_content:
            last_thought = f"对 JoJo 说了：{said_content[:30]}"
        else:
            last_thought = "沉默，没什么想说的"

    # 写日记
    if said_content:
        add_journal(observation="", thought=last_thought, action=f"对 JoJo 说：{said_content}")
    else:
        add_journal(observation="", thought=last_thought, action=last_action or "选择沉默")

    # 保存内部状态（现在一定有值了）
    set_inner_state(last_thought=last_thought)


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

def get_inner_state():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT last_thought, current_focus, pending_intent, pending_intent_due, updated_at FROM agent_inner_state WHERE id=1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}


def set_inner_state(last_thought=None, current_focus=None, pending_intent=None, pending_intent_due=None):
    """更新内部状态。传 None 的字段保持原值"""
    current = get_inner_state()
    new = {
        "last_thought": last_thought if last_thought is not None else current.get("last_thought"),
        "current_focus": current_focus if current_focus is not None else current.get("current_focus"),
        "pending_intent": pending_intent if pending_intent is not None else current.get("pending_intent"),
        "pending_intent_due": pending_intent_due if pending_intent_due is not None else current.get("pending_intent_due"),
    }
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE agent_inner_state SET last_thought=?, current_focus=?, pending_intent=?, pending_intent_due=?, updated_at=? WHERE id=1",
        (new["last_thought"], new["current_focus"], new["pending_intent"], new["pending_intent_due"], datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def add_journal(observation="", thought="", action=""):
    """记一条她的日记"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO agent_journal (observation, thought, action, created_at) VALUES (?, ?, ?, ?)",
        (observation, thought, action, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def load_recent_journal(limit=5):
    """读最近 N 条日记"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT observation, thought, action, created_at FROM agent_journal ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]