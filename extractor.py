import json
from llm import extract_chat

EXTRACT_PROMPT = """
你是一个记忆抽取器。从对话中抽取值得长期记住的信息。

规则：
- 只抽关于用户（JoJo）的稳定事实、长期偏好、里程碑事件、强烈情绪。
- content 必须以"JoJo"开头，不要用"用户"、"我"、"他"等词作为主语。
  例如写"JoJo 喜欢黑色"，不要写"用户喜欢黑色"或"我喜欢黑色"。
- 不要抽：寒暄、闲聊、今天做了什么、当下正在做的事、项目进度、技术讨论、AI 自己的事。
- 但如果对话里确实包含了用户的偏好、事实、情绪、事件，**尽量不要漏掉**。
- 宁可抽出来，也不要因为"不确定"就丢。
- type 只能是：fact, preference, event, emotion

importance 评分标准：
- 0.9-1.0：姓名、生日、长期身份、重大人生事件（搬家、升学、失恋、重病、亲人离世）
- 0.7-0.8：长期稳定的偏好、重要的长期关系、反复出现的强烈情绪
- 0.4-0.6：一般偏好、普通事件、日常情绪
- 0.1-0.3：模糊信息、可能变化的偏好、一次性事件

重要判断：
- 如果一条信息过一段时间会自己失效，importance 必须低于 0.4。
- 如果信息是关于"用户正在做什么项目、任务、学习内容"，importance 必须低于 0.3。
- 不确定的时候，给 0.5，不要给低于 0.3。

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
    raw = extract_chat([{"role": "user", "content": prompt}])


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
            # 规范化主语
            content = m.get("content", "")
            content = content.replace("用户", "JoJo").replace("我", "JoJo")
            m["content"] = content
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