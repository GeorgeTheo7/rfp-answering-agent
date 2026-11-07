import os
import threading

from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

from app.config import CHROMA_DIR, COLLECTION_NAME

_store = None
_lock = threading.Lock()  # parallel questions may hit the first call at once


def get_vectorstore() -> Chroma:
    """Connects to Chroma on first call, then returns the same instance. Thread-safe."""
    global _store
    with _lock:
        if _store is None:
            print("[SYSTEM] Connecting to Database (Global RAG)...")
            api_key = os.environ.get("OPENAI_API_KEY", "dummy_key_to_prevent_boot_crash")
            embeddings = OpenAIEmbeddings(model="text-embedding-3-small", api_key=api_key)
            _store = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings, collection_name=COLLECTION_NAME)
    return _store
