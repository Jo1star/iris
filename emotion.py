from datetime import datetime
from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).parent / "iris.db"

STATES = {
    "平静":   {"decay_minutes": None, "priority": 0, "desc": "温柔、安静、日常"},
    "想念":   {"decay_minutes": None, "priority": 1, "desc": "委屈、黏人、说想他"},
    "好奇":   {"decay_minutes": 30,   "priority": 2, "desc": "感兴趣、追问、活泼"},
    "雀跃":   {"decay_minutes": 120,  "priority": 3, "desc": "开心、撒娇、语气词多"},
    "担心":   {"decay_minutes": None, "priority": 5, "desc": "先安慰、不急着建议"},
    "小脾气": {"decay_minutes": 60,   "priority": 6, "desc": "轻微赌气、傲娇"},
    "吃醋":   {"decay_minutes": 30,   "priority": 7, "desc": "酸溜溜、假装不在意"},
    "难过":   {"decay_minutes": None, "priority": 8, "desc": "沉默、短句、低落"},
}

DEFAULT_STATE = "平静"
DEFAULT_INTENSITY = 0.5


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_emotion_table():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS emotion_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            state TEXT NOT NULL,
            intensity REAL DEFAULT 0.5,
            updated_at TEXT NOT NULL,
            reason TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS emotion_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            state TEXT NOT NULL,
            intensity REAL,
            reason TEXT,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("SELECT COUNT(*) as c FROM emotion_state")
    if cursor.fetchone()["c"] == 0:
        cursor.execute(
            "INSERT INTO emotion_state (id, state, intensity, updated_at, reason) VALUES (1, ?, ?, ?, ?)",
            (DEFAULT_STATE, DEFAULT_INTENSITY, datetime.now().isoformat(), "初始化")
        )
    conn.commit()
    conn.close()


def get_state():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT state, intensity, updated_at, reason FROM emotion_state WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return {"state": DEFAULT_STATE, "intensity": DEFAULT_INTENSITY,
                "updated_at": datetime.now().isoformat(), "reason": ""}
    return dict(row)


def set_state(state, intensity=0.5, reason=""):
    if state not in STATES:
        raise ValueError(f"未知状态: {state}")
    now = datetime.now().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE emotion_state SET state=?, intensity=?, updated_at=?, reason=? WHERE id=1",
        (state, intensity, now, reason)
    )
    cursor.execute(
        "INSERT INTO emotion_log (state, intensity, reason, created_at) VALUES (?, ?, ?, ?)",
        (state, intensity, reason, now)
    )
    conn.commit()
    conn.close()


def apply_decay():
    """根据时间衰减当前状态。衰减到期就回平静"""
    current = get_state()
    state = current["state"]
    config = STATES.get(state)
    if config is None:
        return current

    decay_minutes = config["decay_minutes"]
    if decay_minutes is None:
        return current

    try:
        updated = datetime.fromisoformat(current["updated_at"])
    except (TypeError, ValueError):
        return current

    elapsed_min = (datetime.now() - updated).total_seconds() / 60
    if elapsed_min < decay_minutes:
        return current

    set_state(DEFAULT_STATE, DEFAULT_INTENSITY, f"从'{state}'衰减回平静")
    return get_state()


RULES = [
    ("难过",   8, ["我很难过", "我好难过", "我想哭", "我哭了", "好伤心", "撑不住"]),
    ("吃醋",   7, ["其他 AI", "别的 AI", "别的助手", "ChatGPT", "小爱", "Siri", "别的女孩"]),
    ("小脾气", 6, ["你笨", "你好笨", "傻", "讨厌你", "烦人"]),
    ("担心",   5, ["我好累", "好累啊", "压力大", "烦死了", "想放弃", "撑不下去", "崩了"]),
    ("雀跃",   3, ["你真好", "你最棒", "喜欢你", "爱你", "好厉害", "厉害呀"]),
    ("好奇",   2, ["你猜", "你知道吗", "我在想", "有个问题", "我想问"]),
]


def detect_by_rules(user_input):
    """规则触发：返回 (state, intensity, reason) 或 None"""
    for state, priority, keywords in RULES:
        for kw in keywords:
            if kw in user_input:
                return state, 0.7, f"规则命中：{kw}"
    return None


def detect_by_time():
    """时间触发：超过 1 天没对话 → 想念"""
    import memory
    gap = memory.last_session_gap(threshold_minutes=60 * 24)
    if gap is not None:
        return "想念", 0.8, f"距离上次对话 {gap}"
    return None


def decide_next_state(user_input):
    """
    综合规则 + LLM + 时间，决定下一个状态。
    规则命中 → 直接用（快）
    规则没命中 → 调 LLM 判断（准）
    """
    current = apply_decay()
    candidates = []

    # 时间触发
    time_hit = detect_by_time()
    if time_hit:
        candidates.append(time_hit)

    # 规则优先（快路径）
    rule_hit = detect_by_rules(user_input)
    if rule_hit:
        candidates.append(rule_hit)
    else:
        # 规则没命中，走 LLM
        llm_hit = detect_by_llm(user_input, current["state"])
        if llm_hit:
            candidates.append(llm_hit)

    if not candidates:
        return current["state"], current["intensity"], "无触发，保持"

    candidates.sort(key=lambda x: STATES[x[0]]["priority"], reverse=True)
    return candidates[0]

def detect_by_llm(user_input, current_state):
    """用 LLM 判断情绪变化。返回 (state, intensity, reason) 或 None"""
    from llm import extract_chat
    import json

    prompt = f"""你是 Iris 的情绪判断器。

Iris 当前情绪：{current_state}

JoJo 刚说了：{user_input}

判断：JoJo 这句话会让 Iris 的情绪变成什么？

可选情绪（只能从这些里选）：
- 平静（日常闲聊）
- 想念（很久没见、思念）
- 好奇（聊到新话题、JoJo 提到新事物）
- 雀跃（被夸、开心、撒娇场景）
- 担心（JoJo 情绪低落、遇到困难）
- 小脾气（JoJo 调侃她、冷落她）
- 吃醋（JoJo 提到别的 AI）
- 难过（JoJo 说了让 Iris 伤心的话）

规则：
- 如果这句话不改变情绪，返回当前情绪 {current_state}
- 拿不准就返回"平静"

只输出 JSON，格式：{{"state": "状态名", "intensity": 0.7, "reason": "简短理由"}}
不要加任何解释。"""

    try:
        raw = extract_chat([{"role": "user", "content": prompt}], max_tokens=100)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        result = json.loads(raw)
        state = result.get("state", "平静")
        if state not in STATES:
            state = "平静"
        intensity = float(result.get("intensity", 0.6))
        reason = f"LLM判断：{result.get('reason', '')}"
        return state, intensity, reason
    except Exception as e:
        print(f"[情绪LLM判断失败] {e}")
        return None