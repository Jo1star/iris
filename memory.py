import sqlite3
from datetime import datetime
from pathlib import Path
import vector_store

DB_PATH = Path(__file__).parent / "iris.db"

SIM_MERGE = 0.90   # 相似度 > 0.90 → 合并，不新增
SIM_GRAY  = 0.70   # 0.70 ~ 0.90 → 新增但打印日志，观察用

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def migrate_db():
    """给已有表加新字段，不存在才加，重复运行也安全"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(memories)")
    columns = [row["name"] for row in cursor.fetchall()]

    if "last_accessed" not in columns:
        cursor.execute("ALTER TABLE memories ADD COLUMN last_accessed TEXT")

    if "archived" not in columns:
        cursor.execute("ALTER TABLE memories ADD COLUMN archived INTEGER DEFAULT 0")

    conn.commit()
    conn.close()


def init_db():
    """建表，如果已经存在就跳过"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            content TEXT NOT NULL,
            importance REAL DEFAULT 0.5,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

    migrate_db()


def save_message(role, content):
    """保存一条消息"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (role, content, created_at) VALUES (?, ?, ?)",
        (role, content, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def load_recent_messages(limit=50):
    """读取最近 N 条消息，按时间正序返回"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()

    # 倒序读出来的，反转成正序
    messages = [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
    return messages


def clear_all():
    """清空所有历史"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages")
    conn.commit()
    conn.close()


def count_messages():
    """统计消息总数"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM messages")
    n = cursor.fetchone()["c"]
    conn.close()
    return n

def save_memory(mem_type, content, importance=0.5):
    content = content.strip()
    if not content:
        return "empty"

    # 第一层：语义去重
    similar = vector_store.find_similar(content, limit=1)
    if similar:
        top = similar[0]
        sim = top["similarity"]
        if sim > SIM_MERGE:
            _merge_memory(top["id"], importance)
            return "merged"
        elif sim >= SIM_GRAY:
            print(f"[dedup 灰区] sim={sim:.3f} 新: {content} | 旧: {top['content']}")

    # 第二层：字符串模糊去重（兜底）
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM memories WHERE content = ? OR content LIKE ? OR ? LIKE '%' || content || '%'",
        (content, f"%{content}%", content)
    )
    existing = cursor.fetchone()
    if existing:
        conn.close()
        _merge_memory(existing["id"], importance)
        return "merged_str"

    # 新增
    cursor.execute(
        "INSERT INTO memories (type, content, importance, created_at, last_accessed, archived) "
        "VALUES (?, ?, ?, ?, ?, 0)",
        (mem_type, content, importance,
         datetime.now().isoformat(), datetime.now().isoformat())
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    vector_store.add_memory(new_id, content)
    return "inserted"


def _merge_memory(memory_id, importance):
    """把新记忆的重要性合并到旧记忆上，同时刷新 last_accessed"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT importance FROM memories WHERE id = ?", (memory_id,))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        return
    new_imp = max(row["importance"], importance)
    cursor.execute(
        "UPDATE memories SET importance = ?, last_accessed = ? WHERE id = ?",
        (new_imp, datetime.now().isoformat(), memory_id)
    )
    conn.commit()
    conn.close()


def load_memories(limit=30, include_archived=False):
    """读取最近的记忆，默认不含归档"""
    conn = get_connection()
    cursor = conn.cursor()

    if include_archived:
        cursor.execute(
            "SELECT id, type, content, importance FROM memories ORDER BY id DESC LIMIT ?",
            (limit,)
        )
    else:
        cursor.execute(
            "SELECT id, type, content, importance FROM memories WHERE archived = 0 ORDER BY id DESC LIMIT ?",
            (limit,)
        )

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def count_archived():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM memories WHERE archived = 1")
    n = cursor.fetchone()["c"]
    conn.close()
    return n

def touch_memory(memory_id):
    """更新最后访问时间"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE memories SET last_accessed = ? WHERE id = ?",
        (datetime.now().isoformat(), memory_id)
    )
    conn.commit()
    conn.close()

def count_memories():
    """统计记忆条数"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM memories")
    n = cursor.fetchone()["c"]
    conn.close()
    return n


def clear_memories():
    """清空所有提炼记忆"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM memories")
    conn.commit()
    conn.close()

    # 清空向量库
    all_ids = vector_store.collection.get()["ids"]
    if all_ids:
        vector_store.collection.delete(ids=all_ids)

def apply_time_decay(decay_days=30, archive_threshold=0.2):
    """对长期没被访问的记忆做衰减。
    - 超过 decay_days 天没被访问，importance 减半
    - 衰减后 importance 低于 archive_threshold，归档
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, importance, last_accessed, created_at
        FROM memories
        WHERE archived = 0
    """)
    rows = cursor.fetchall()

    now = datetime.now()
    archived_count = 0

    for row in rows:
        # 用 last_accessed，没有就用 created_at
        last = row["last_accessed"] or row["created_at"]
        try:
            last_time = datetime.fromisoformat(last)
        except (TypeError, ValueError):
            continue

        days = (now - last_time).days
        if days < decay_days:
            continue

        # 每过 decay_days 天，importance 减半
        factor = 0.5 ** (days / decay_days)
        new_importance = row["importance"] * factor

        if new_importance < archive_threshold:
            cursor.execute(
                "UPDATE memories SET archived = 1 WHERE id = ?",
                (row["id"],)
            )
            archived_count += 1
        else:
            cursor.execute(
                "UPDATE memories SET importance = ? WHERE id = ?",
                (new_importance, row["id"])
            )

    conn.commit()
    conn.close()
    return archived_count

def last_session_gap(threshold_minutes=30):
    """返回'距上次对话多久'的中文描述；间隔小于阈值返回 None"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT created_at FROM messages ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    try:
        last = datetime.fromisoformat(row["created_at"])
    except (TypeError, ValueError):
        return None
    delta = datetime.now() - last
    minutes = delta.total_seconds() / 60
    if minutes < threshold_minutes:
        return None
    if minutes < 60:
        return f"约 {int(minutes)} 分钟"
    hours = minutes / 60
    if hours < 24:
        return f"约 {int(hours)} 小时"
    days = hours / 24
    return f"约 {int(days)} 天"