import threading
import time

from app import store


def test_concurrent_first_calls_connect_once(monkeypatch):
    created = []

    class SlowChroma:
        def __init__(self, **kwargs):
            time.sleep(0.2)  # slow connect widens the race window
            created.append(self)

    monkeypatch.setattr(store, "Chroma", SlowChroma)
    monkeypatch.setattr(store, "OpenAIEmbeddings", lambda **kwargs: None)
    monkeypatch.setattr(store, "_store", None)  # restored after the test

    results = []
    threads = [threading.Thread(target=lambda: results.append(store.get_vectorstore())) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(created) == 1
    assert all(r is created[0] for r in results)
