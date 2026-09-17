import memory
import vector_store

memory.init_db()

print("=== 测试前 ===")
for m in memory.load_memories(limit=20):
    print(f"  {m['id']} [{m['type']}] {m['content']} ({m['importance']:.2f})")

print("\n=== 新增一条 'JoJo 喜欢画画' ===")
r = memory.save_memory("preference", "JoJo 喜欢画画", 0.6)
print(f"结果: {r}")

print("\n=== 测试后 ===")
for m in memory.load_memories(limit=20):
    print(f"  {m['id']} [{m['type']}] {m['content']} ({m['importance']:.2f})")