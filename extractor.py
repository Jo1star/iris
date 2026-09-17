import json
from llm import chat

EXTRACT_PROMPT = """
你是一个记忆抽取器。从对话中抽取值得长期记住的信息。

规则：
- 只抽关于用户（JoJo）的稳定事实、长期偏好、里程碑事件、强烈情绪。
- 不要抽：寒暄、闲聊、今天做了什么、当下正在做的事、项目进度、技术讨论。
- type 只能是：fact, preference, event, emotion

importance 评分标准：
- 0.9-1.0：姓名、生日、长期身份、重大人生事件（搬家、升学、失恋、重病、亲人离世）
- 0.7-0.8：长期稳定的偏好、重要的长期关系、反复出现的强烈情绪
- 0.4-0.6：一般偏好、普通事件、日常情绪
- 0.1-0.3：模糊信息、可能变化的偏好、一次性事件

重要判断：
- 如果一条信息过一段时间会自己失效，importance 必须低于 0.4。
- 如果信息是关于“用户正在做什么项目、任务、学习内容”，importance 必须低于 0.3。
- 如果不确定，宁可给低分，也不要给高分。

如果没有值得长期记的，输出 []。
只输出 JSON 数组，不要加任何解释。

对话：
用户：{user_input}
Iris：{assistant_reply}
"""


def extract(user_input, assistant_reply):
    prompt = EXTRACT_PROMPT.format(
        user_input=user_input,
        assistant_reply=assistant_reply
    )
    raw = chat([{"role": "user", "content": prompt}])


    # 去掉可能的 markdown 代码块
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        memories = json.loads(raw)
        if not isinstance(memories, list):
            return []

        # 过滤：低分事件不存
        cleaned = []
        for m in memories:
            m_type = m.get("type", "fact")
            try:
                imp = float(m.get("importance", 0.5))
            except (TypeError, ValueError):
                imp = 0.5

            # 事件类低于 0.5 直接丢
            if m_type == "event" and imp < 0.5:
                continue

            # 任何类型低于 0.2 直接丢
            if imp < 0.2:
                continue

            m["importance"] = imp
            cleaned.append(m)

        return cleaned
    except json.JSONDecodeError:
        return []