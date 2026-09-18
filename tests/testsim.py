import vector_store
import memory

memory.init_db()
memory.clear_memories()

# 先入库一条
memory.save_memory("preference", "JoJo 喜欢画画", 0.6)

# 然后用几条不同的句子查相似度
tests = [
    "JoJo 不再喜欢画画了",   # 期望：语义相反，但相似度可能低
    "JoJo 喜欢绘画",          # 期望：高
    "JoJo 爱好是画画",        # 期望：高
    "JoJo 喜欢音乐",          # 期望：低
    "JoJo 不喜欢画画",        # 期望：语义相反
]

for t in tests:
    result = vector_store.find_similar(t, limit=1)
    if result:
        print(f"sim={result[0]['similarity']:.3f}  查询: {t}")
        print(f"                       匹配到: {result[0]['content']}")
        print()
