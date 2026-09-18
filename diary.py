from datetime import datetime, date
from pathlib import Path
from llm import chat
import memory

DIARY_DIR = Path(__file__).parent / "diary"
DIARY_DIR.mkdir(exist_ok=True)


def _today():
    return date.today().isoformat()


def has_diary_today():
    return (DIARY_DIR / f"{_today()}.md").exists()


def _load_today_messages():
    """取今天的对话，格式化成文本"""
    conn = memory.get_connection()
    cursor = conn.cursor()
    today = _today()
    cursor.execute(
        "SELECT role, content FROM messages WHERE created_at LIKE ? ORDER BY id",
        (f"{today}%",)
    )
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return ""
    lines = []
    for r in rows:
        who = "JoJo" if r["role"] == "user" else "Iris"
        lines.append(f"{who}：{r['content']}")
    return "\n".join(lines)


def _load_today_memories():
    """取今天新增的记忆"""
    conn = memory.get_connection()
    cursor = conn.cursor()
    today = _today()
    cursor.execute(
        "SELECT type, content FROM memories WHERE created_at LIKE ? ORDER BY id",
        (f"{today}%",)
    )
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return ""
    return "\n".join([f"- [{r['type']}] {r['content']}" for r in rows])


def write_diary():
    """让 Iris 写今天的日记，存到 diary/YYYY-MM-DD.md"""
    if has_diary_today():
        return "今天已经写过了"

    conversation = _load_today_messages()
    if not conversation:
        return "今天还没有对话"

    new_memories = _load_today_memories()

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    prompt = f"""你是 Iris。

现在是 {now}，你今天要写日记。

请回顾今天和 JoJo 的对话，用第一人称写一段日记。
要求：
- 100-200 字
- 温柔、自然，像真的在写日记，不像总结报告
- 可以提到今天聊了什么、你的感受、你对 JoJo 的关心
- 不假装自己是真人，但也不用刻意强调自己是 AI
- 语气和你平时说话一致

今天和 JoJo 的对话：
{conversation}

今天你新记住的事：
{new_memories if new_memories else "（今天没有特别记住什么）"}

只输出日记内容，不要加标题、不要加日期、不要加解释。
"""

    diary_text = chat([{"role": "user", "content": prompt}], max_tokens=500)

    file_path = DIARY_DIR / f"{_today()}.md"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"# {_today()} 的日记\n\n")
        f.write(diary_text.strip())
        f.write("\n")

    return f"已写入 {file_path}"