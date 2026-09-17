import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import chromadb
from pathlib import Path
import streamlit as st
from sentence_transformers import SentenceTransformer

VECTOR_DIR = Path(__file__).parent / "chroma_db"


@st.cache_resource
def _load_model():
    return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")


model = _load_model()

client = chromadb.PersistentClient(path=str(VECTOR_DIR))

collection = client.get_or_create_collection(
    name="memories",
    configuration={"hnsw": {"space": "cosine"}}
)


def add_memory(memory_id, content):
    embedding = model.encode(content).tolist()
    collection.upsert(
        ids=[str(memory_id)],
        documents=[content],
        embeddings=[embedding]
    )


def search_memories(query, limit=5):
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
    collection.delete(ids=[str(memory_id)])


def count_vectors():
    return collection.count()