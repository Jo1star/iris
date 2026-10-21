"""一键打包所有核心代码到 _snapshot.md"""
import os

FILES = [
    # 人格与内核
    "persona.py", "persona_dynamic.md", "emotion.py",
    # 记忆系统
    "memory.py", "extractor.py", "vector_store.py",
    # Agent 内核
    "agent_core.py", "agent_tools.py",
    # 接口层
    "llm.py", "service.py", "server.py", "web/index.html", "diary.py",
    # MC 接入
    "mc_bridge.py",
]

def lang_of(f):
    if f.endswith(".py"): return "python"
    if f.endswith(".html"): return "html"
    if f.endswith(".md"): return "markdown"
    if f.endswith(".js"): return "javascript"
    return ""

out = ["# Iris 项目代码快照\n"]
for f in FILES:
    if not os.path.exists(f):
        out.append(f"\n## {f}  （不存在，跳过）\n")
        continue
    out.append(f"\n## 文件：{f}\n")
    out.append(f"```{lang_of(f)}")
    with open(f, "r", encoding="utf-8") as fh:
        out.append(fh.read())
    out.append("```\n")

with open("_snapshot.md", "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))

size = os.path.getsize("_snapshot.md")
print(f"完成：_snapshot.md（{size/1024:.1f} KB，约 {sum(1 for _ in open('_snapshot.md', encoding='utf-8'))} 行）")