import os

# 必须在 import sentence_transformers 之前设置
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import chromadb
from pathlib import Path
from sentence_transformers import SentenceTransformer

VECTOR_DIR = Path(__file__).parent / "chroma_db"

# 加载本地嵌入模型（首次运行会自动下载）
model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
# 持久化客户端，数据存到磁盘，重启不丢
client = chromadb.PersistentClient(path=str(VECTOR_DIR))

collection = client.get_or_create_collection(
    name="memories",
    configuration={"hnsw": {"space": "cosine"}}
)


def add_memory(memory_id, content):
    """把一条记忆写入向量库"""
    embedding = model.encode(content).tolist()
    collection.upsert(
        ids=[str(memory_id)],
        documents=[content],
        embeddings=[embedding]
    )


def search_memories(query, limit=5):
    """向量语义检索，返回最相关的记忆"""
    if collection.count() == 0:
        return []

    query_embedding = model.encode(query).tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(limit, collection.count())
    )

    if not results["documents"] or not results["documents"][0]:
        return []

    return results["documents"][0]


def delete_memory(memory_id):
    """从向量库删除一条记忆"""
    collection.delete(ids=[str(memory_id)])


def count_vectors():
    """统计向量库条数"""
    return collection.count()