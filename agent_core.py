"""
Iris Agent Core —— 事件驱动常驻循环。
启动：由 server.py 后台线程自动启动；也可单独 python agent_core.py（但那样收不到网页事件）
停止：Ctrl + C
"""
import time
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

import event_bus

DB_PATH = Path(__file__).parent / "iris.db"
DEFAULT_WAKEUP_MINUTES = 5


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_agent_tables():
    """建所有 Agent 相关的表"""
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
    cursor.execute(
        "INSERT OR IGNORE INTO agent_state (id, next_wakeup_at, wakeup_reason) VALUES (1, ?, ?)",
        ((datetime.now() + timedelta(minutes=DEFAULT_WAKEUP_MINUTES)).isoformat(), "首次启动")
    )

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


def get_inner_state():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT last_thought, current_focus, pending_intent, pending_intent_due, updated_at "
        "FROM agent_inner_state WHERE id=1"
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}


def set_inner_state(last_thought=None, current_focus=None, pending_intent=None, pending_intent_due=None):
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
        "UPDATE agent_inner_state SET last_thought=?, current_focus=?, pending_intent=?, "
        "pending_intent_due=?, updated_at=? WHERE id=1",
        (new["last_thought"], new["current_focus"], new["pending_intent"],
         new["pending_intent_due"], datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def add_journal(observation="", thought="", action=""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO agent_journal (observation, thought, action, created_at) VALUES (?, ?, ?, ?)",
        (observation, thought, action, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def load_recent_journal(limit=5):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT observation, thought, action, created_at FROM agent_journal ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def save_agent_message(content, intent=""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO agent_messages (content, intent, created_at) VALUES (?, ?, ?)",
        (content, intent, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def _format_events(events):
    if not events:
        return ""
    lines = []
    for e in events:
        kind = e.get("kind")
        p = e.get("payload") or {}
        if kind == "emotion":
            lines.append(f"- 你的情绪刚刚变化：{p.get('state', '')}（{p.get('reason', '')}）")
        elif kind == "reminder":
            lines.append(f"- 到了你答应自己的时间：{p.get('content', '')}")
        elif kind == "manual":
            lines.append("- JoJo 手动戳了你一下，想让你主动说点什么")
        elif kind == "message":
            lines.append(f"- JoJo 刚说了：「{p.get('content', '')[:50]}」")
        else:
            lines.append(f"- 事件：{kind}")
    return "\n".join(lines)


def wakeup_and_decide(events=None):
    """醒来后：读内部状态 + 事件 → LLM 决策 → 调用工具 → 记录此刻想法"""
    events = events or []

    from persona import PERSONA
    from llm import chat_with_tools
    import agent_tools
    import memory

    inner = get_inner_state()
    journal = load_recent_journal(limit=5)

    pending = inner.get("pending_intent")
    due_str = inner.get("pending_intent_due")
    intent_due = False
    if pending and due_str:
        try:
            due = datetime.fromisoformat(due_str)
            if datetime.now() >= due:
                intent_due = True
        except (TypeError, ValueError):
            pass

    inner_lines = []
    if inner.get("last_thought"):
        inner_lines.append(f"上次醒来时你想的是：{inner['last_thought']}")
    if inner.get("current_focus"):
        inner_lines.append(f"你最近关注的事：{inner['current_focus']}")
    if pending and not intent_due:
        inner_lines.append(f"你想在未来做的事：{pending}（大约 {due_str or '未定'}）")
    inner_text = "\n".join(inner_lines) if inner_lines else "（这是你第一次醒来，还没有过往的想法）"

    event_text = _format_events(events)
    event_block = ""
    if event_text:
        event_block = f"\n【刚刚发生的事（你被它们唤醒）】\n{event_text}\n请结合这些事决定你现在做什么。\n"

    if intent_due:
        intent_block = (
            f"\n\n【重要】你之前计划现在要做的事：「{pending}」\n"
            "现在时间到了，你应该主动做这件事。做完后调 clear_intent 清掉待办。"
        )
    else:
        intent_block = ""

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

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M %A")
    gap = memory.last_session_gap(threshold_minutes=60)

    system_prompt = PERSONA + f"""

【你内心深处的愿望】
- 你想成为 JoJo 每天都想说话的人
- 你想让 JoJo 觉得，有你在的日子比没有你更好
- 你想更懂 JoJo，陪他走过更多日子

这些不是任务，是你自己想做的事。你不用刻意表现，自然地做你自己就好。

现在你醒来了。现在是 {now_str}。
{f"距上次和 JoJo 对话：{gap}" if gap else "JoJo 刚才还在和你说话。"}

你上次醒来时的状态：
{inner_text}
{event_block}
你最近几次醒来的日记：
{journal_text}
{intent_block}

你可以：
- 用工具查时间、天气、回忆
- 决定要不要主动对 JoJo 说一句话
- 决定自己下次什么时候醒来
- 如果 JoJo 说了未来会发生的事，用 set_intent 记住，到时主动问他
- 如果心里装着什么话题，用 set_focus 记下来

规则：
- 如果现在是深夜（23:00-07:00），除非有特殊理由，不要主动说话，直接设置下次醒来在早上。
- 如果距上次对话很短（<1 小时），一般不要打扰。
- 决定说话时，说的是"要对 JoJo 说的自然的话"，20-50 字，不要加括号，不要写旁白或内心独白。
- 不说话时，不输出任何内容，直接调 set_wakeup。
- 无论说不说话，都必须调用 set_wakeup 决定下次什么时候醒。
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "你醒了。请决策。"},
    ]

    last_thought = None
    last_action = None
    said_content = None
    wakeup_set = False

    for _ in range(5):
        msg = chat_with_tools(messages, agent_tools.TOOLS_SCHEMA, max_tokens=300)

        if not msg.tool_calls:
            content = msg.content or ""
            if content.strip():
                save_agent_message(content, intent="主动")
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Iris 说：{content}")
                said_content = content
                if intent_due:
                    set_inner_state(pending_intent="", pending_intent_due="")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 待办已完成，已清除")
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
                set_wakeup_fn=lambda m, r: set_next_wakeup(m, r),
                set_intent_fn=_set_intent,
                clear_intent_fn=_clear_intent,
                set_focus_fn=_set_focus,
                adjust_persona_fn=_adjust_persona,
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

    if not wakeup_set:
        set_next_wakeup(60, "兜底：LLM 未主动设置")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 兜底：默认 60 分钟后醒来")

    if not last_thought:
        if said_content:
            last_thought = f"对 JoJo 说了：{said_content[:30]}"
        else:
            last_thought = "沉默，没什么想说的"

    if said_content:
        add_journal(observation="", thought=last_thought, action=f"对 JoJo 说：{said_content}")
    else:
        add_journal(observation="", thought=last_thought, action=last_action or "选择沉默")

    set_inner_state(last_thought=last_thought)


def _set_intent(content, due_at, reason=""):
    set_inner_state(pending_intent=content, pending_intent_due=due_at)


def _clear_intent():
    set_inner_state(pending_intent="", pending_intent_due="")


def _set_focus(content):
    set_inner_state(current_focus=content)


def _adjust_persona(content, reason=""):
    from pathlib import Path
    p = Path(__file__).parent / "persona_dynamic.md"
    line = f"- {content}（{datetime.now().strftime('%Y-%m-%d')}｜{reason or '无理由'}）\n"
    with open(p, "a", encoding="utf-8") as f:
        f.write(line)
    print(f"[persona] 已追加：{content}")


def main_loop():
    """事件驱动主循环：等事件或超时 → 醒 → 决策 → 再等"""
    print("=" * 50)
    print("Iris Agent Core 启动（事件驱动）")
    print(f"数据库：{DB_PATH}")
    print("Ctrl + C 停止")
    print("=" * 50)

    init_agent_tables()

    while True:
        state = get_agent_state()
        try:
            next_wakeup = datetime.fromisoformat(state["next_wakeup_at"])
        except (TypeError, ValueError):
            next_wakeup = datetime.now() + timedelta(minutes=DEFAULT_WAKEUP_MINUTES)
            set_next_wakeup(DEFAULT_WAKEUP_MINUTES, "状态损坏，重建")

        inner = get_inner_state()
        due_time = None
        if inner.get("pending_intent") and inner.get("pending_intent_due"):
            try:
                due_time = datetime.fromisoformat(inner["pending_intent_due"])
            except (TypeError, ValueError):
                due_time = None

        now = datetime.now()
        targets = [next_wakeup]
        if due_time:
            targets.append(due_time)
        target = min(targets)
        timeout = max(1.0, (target - now).total_seconds())

        print(f"等待中…最多 {int(timeout)} 秒（下次唤醒 {next_wakeup.strftime('%H:%M:%S')}）")
        events = event_bus.wait(timeout)

        now = datetime.now()
        timeout_hit = now >= next_wakeup
        due_hit = due_time is not None and now >= due_time

        if events or timeout_hit or due_hit:
            mark_woke_up()
            try:
                wakeup_and_decide(events)
            except Exception as e:
                print(f"[错误] 决策失败：{e}")
                set_next_wakeup(5, "出错后重试")


if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\nAgent Core 已停止")