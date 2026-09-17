import sqlite3
from datetime import datetime
from pathlib import Path
import vector_store

DB_PATH = Path(__file__).parent / "iris.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
    """保存一条记忆，同时写入 SQLite 和向量库"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, importance FROM memories WHERE content = ? OR content LIKE ? OR ? LIKE '%' || content || '%'",
        (content, f"%{content}%", content)
    )
    existing = cursor.fetchone()

    if existing:
        new_importance = max(existing["importance"], importance)
        cursor.execute(
            "UPDATE memories SET importance = ? WHERE id = ?",
            (new_importance, existing["id"])
        )
        conn.commit()
        conn.close()
        # 更新向量库
        vector_store.add_memory(existing["id"], content)
    else:
        cursor.execute(
            "INSERT INTO memories (type, content, importance, created_at) VALUES (?, ?, ?, ?)",
            (mem_type, content, importance, datetime.now().isoformat())
        )
        new_id = cursor.lastrowid
        conn.commit()
        conn.close()
        # 写入向量库
        vector_store.add_memory(new_id, content)


def load_memories(limit=30):
    """读取最近的记忆"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT type, content, importance FROM memories ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


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
