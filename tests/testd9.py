import memory
import vector_store

memory.init_db()

print("=== 清空测试数据 ===")
memory.clear_memories()

print("\n=== 第 1 条：存入 'JoJo 喜欢画画' ===")
r1 = memory.save_memory("preference", "JoJo 喜欢画画", 0.6)
print(f"结果: {r1}")

print("\n=== 第 2 条：存入 'JoJo 不再喜欢画画了' ===")
r2 = memory.save_memory("preference", "JoJo 不再喜欢画画了", 0.7)
print(f"结果: {r2}")

print("\n=== 当前所有记忆（含归档） ===")
for m in memory.load_memories(limit=20, include_archived=True):
    print(f"  {m['id']} [{m['type']}] {m['content']} ({m['importance']:.2f})")

print("\n=== 检索时能看到的记忆（不含归档） ===")
for m in memory.load_memories(limit=20):
    print(f"  {m['id']} [{m['type']}] {m['content']} ({m['importance']:.2f})")