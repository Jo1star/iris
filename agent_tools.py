"""Iris 能用的工具。每个函数是一个工具，配套一份给 LLM 看的 schema。"""
import requests
from datetime import datetime
import memory


# ============ 工具实现 ============

def tool_get_time():
    """拿当前时间"""
    now = datetime.now()
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return f"{now.strftime('%Y-%m-%d %H:%M')} {weekdays[now.weekday()]}"


def tool_get_weather(city="西安"):
    """查天气（Open-Meteo，免费不用 Key）"""
    try:
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "zh"},
            timeout=10
        ).json()
        if not geo.get("results"):
            return f"找不到城市：{city}"
        loc = geo["results"][0]

        weather = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": loc["latitude"],
                "longitude": loc["longitude"],
                "current": "temperature_2m,weather_code",
                "timezone": "Asia/Shanghai"
            },
            timeout=10
        ).json()
        curr = weather["current"]
        temp = curr["temperature_2m"]
        code = curr["weather_code"]
        desc = _weather_desc(code)
        return f"{city}现在 {temp}°C，{desc}"
    except Exception as e:
        return f"查天气失败：{e}"


def _weather_desc(code):
    if code == 0: return "晴"
    if code == 1: return "基本晴"
    if code == 2: return "多云"
    if code == 3: return "阴"
    if code in (45, 48): return "雾"
    if 51 <= code <= 57: return "毛毛雨"
    if 61 <= code <= 67: return "下雨"
    if 71 <= code <= 77: return "下雪"
    if 80 <= code <= 82: return "阵雨"
    if 85 <= code <= 86: return "阵雪"
    if 95 <= code <= 99: return "雷雨"
    return "未知天气"


def tool_recall(query):
    """按关键词检索记忆"""
    results = memory.retrieve_memories(query, limit=3)
    if not results:
        return "没有找到相关记忆"
    return "\n".join([f"- [{r['type']}] {r['content']}" for r in results])


def tool_set_wakeup(minutes, reason=""):
    """设置下次唤醒时间（分钟）。这个工具由 agent_core 注入"""
    raise NotImplementedError("set_wakeup 需要在 agent_core 里注入")

def tool_set_intent(content, due_at, reason="", set_intent_fn=None):
    """设置一个待办：到时间了要主动做的事"""
    if set_intent_fn is None:
        return "set_intent 未注入"
    set_intent_fn(content, due_at, reason)
    return f"已设置待办：{content}（{due_at}）"


def tool_clear_intent(clear_intent_fn=None):
    """清除当前待办（做完或不再需要）"""
    if clear_intent_fn is None:
        return "clear_intent 未注入"
    clear_intent_fn()
    return "已清除当前待办"


def tool_set_focus(content, set_focus_fn=None):
    """设置当前关注的话题"""
    if set_focus_fn is None:
        return "set_focus 未注入"
    set_focus_fn(content)
    return f"已记录当前关注：{content}"


# ============ 给 LLM 的工具 schema（OpenAI 格式） ============

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "获取当前日期、时间和星期。",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询某个城市的实时天气。默认城市是西安。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名，如'西安'、'北京'"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": "从长期记忆里检索关于 JoJo 的信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词或问题"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_wakeup",
            "description": "决定自己下次什么时候醒来。当 JoJo 要求你'过一会提醒我'、'X 分钟后提醒我'时，也用它——你醒来后主动对 JoJo 说那句话即可。",
            "parameters": {
                "type": "object",
                "properties": {
                    "minutes": {"type": "integer", "description": "多少分钟后醒来"},
                    "reason": {"type": "string", "description": "为什么设这个时间，或要提醒 JoJo 什么"}
                },
                "required": ["minutes"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_intent",
            "description": "设置一个未来要主动做的事。比如 JoJo 说明天有面试，你想明天下午问他结果。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "要做的事，如'问 JoJo 面试怎么样'"},
                    "due_at": {"type": "string", "description": "什么时间做，ISO 格式如 '2026-09-20T18:00:00'"},
                    "reason": {"type": "string", "description": "为什么设这个待办"}
                },
                "required": ["content", "due_at"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clear_intent",
            "description": "清除当前待办。当你已经做完了，或这件事不再重要时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_focus",
            "description": "记录你最近在心里关注的事。比如'JoJo 最近很忙'。这个会一直留在你心里，下次醒来还能想起来。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "关注的内容"}
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "adjust_persona",
            "description": "调整你自己的说话方式或行为倾向。当你想改变自己的某种习惯、或发现 JoJo 喜欢你某种说话方式时使用。只能追加，不能删除。例：'说话时可以多撒娇'、'不要每条都追问'。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "一句简短的自我补充"},
                    "reason": {"type": "string", "description": "为什么想加这条"}
                },
                "required": ["content"]
            }
        }
    },
]
# ============ 工具执行器 ============

def execute_tool(name, args, set_wakeup_fn=None, set_intent_fn=None,
                 clear_intent_fn=None, set_focus_fn=None, adjust_persona_fn=None):
    """执行一个工具，返回字符串结果"""
    if name == "get_time":
        return tool_get_time()
    if name == "get_weather":
        return tool_get_weather(args.get("city", "西安"))
    if name == "recall":
        return tool_recall(args.get("query", ""))
    if name == "set_wakeup":
        if set_wakeup_fn is None:
            return "set_wakeup 未注入"
        minutes = int(args.get("minutes", 60))
        set_wakeup_fn(minutes, args.get("reason", ""))
        return f"已设置 {minutes} 分钟后醒来"
    if name == "set_intent":
        return tool_set_intent(
            args.get("content", ""),
            args.get("due_at", ""),
            args.get("reason", ""),
            set_intent_fn
        )
    if name == "clear_intent":
        return tool_clear_intent(clear_intent_fn)
    if name == "set_focus":
        return tool_set_focus(args.get("content", ""), set_focus_fn)
    if name == "adjust_persona":
        return tool_adjust_persona(
            args.get("content", ""),
            args.get("reason", ""),
            adjust_persona_fn
        )
    return f"未知工具：{name}"

def tool_adjust_persona(content, reason="", adjust_persona_fn=None):
    """把自己的一条性格补充写进 persona_dynamic.md"""
    if adjust_persona_fn is None:
        return "adjust_persona 未注入"
    adjust_persona_fn(content, reason)
    return f"已记录：{content}"