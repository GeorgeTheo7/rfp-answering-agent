import asyncio
import time
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient

from app import api
from app.agent.schemas import Answer
from app.main import app


def test_health_returns_ok():
    # No `with` block: the lifespan (startup ingest) does not run.
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_responds_while_a_run_is_in_progress(monkeypatch):
    answers = [Answer(question_id="Q1", question_text="Do you encrypt data?", assigned_analyst="CISO",
                      answer_text="Yes", sources_used=[], category="Security", cost=0.001)]

    def slow_invoke(*args, **kwargs):
        time.sleep(1)  # sync and blocking, like the real graph
        return {"final_answers": answers}

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(api, "rfp_graph", SimpleNamespace(invoke=slow_invoke))

    async def scenario():
        # ASGITransport does not run the lifespan: no startup ingest, no network.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            start = time.perf_counter()

            async def health():
                await asyncio.sleep(0.2)  # let analyze reach the sleep first
                response = await client.get("/api/health")
                return response, time.perf_counter() - start

            analyze, (health_response, health_done) = await asyncio.gather(
                client.post("/api/rfp/analyze", files={"file": ("rfp.pdf", b"unused")}), health())
            return analyze, health_response, health_done

    analyze, health_response, health_done = asyncio.run(scenario())

    assert analyze.status_code == 200
    assert health_response.json() == {"status": "ok"}
    # Measured from the start: if the run blocked the loop, health would finish only after ~1 s.
    assert health_done < 0.6


# --- Demo mode: read-only knowledge base ---

class _FakeStore:
    def __init__(self):
        self.deleted = []

    def get(self, **kwargs):
        return {"ids": ["doc.pdf:h:0"]}

    def delete(self, ids):
        self.deleted.extend(ids)


def _fail_store():
    raise AssertionError("the store must not be touched in demo mode")


def test_config_reports_demo_mode(monkeypatch):
    for flag in (True, False):
        monkeypatch.setattr(api.config, "DEMO_MODE", flag)
        assert TestClient(app).get("/api/config").json() == {"demo_mode": flag}


def test_demo_mode_rejects_kb_writes_without_touching_the_store(monkeypatch):
    monkeypatch.setattr(api.config, "DEMO_MODE", True)
    monkeypatch.setattr(api, "get_vectorstore", _fail_store)
    monkeypatch.setattr(api, "ingest", lambda *a, **k: _fail_store())
    client = TestClient(app)

    responses = [
        client.post("/api/documents/upload", files={"files": ("doc.pdf", b"unused")}),
        client.delete("/api/documents/doc.pdf"),
        client.delete("/api/documents/all"),
    ]

    for response in responses:
        assert response.status_code == 403
        assert response.json() == {"detail": api.DEMO_READ_ONLY_MSG}


def test_deletes_work_when_demo_mode_is_off(monkeypatch):
    store = _FakeStore()
    monkeypatch.setattr(api.config, "DEMO_MODE", False)
    monkeypatch.setattr(api, "get_vectorstore", lambda: store)
    client = TestClient(app)

    assert client.delete("/api/documents/doc.pdf").json() == {"message": "Deleted"}
    assert client.delete("/api/documents/all").json() == {"message": "Deleted"}
    assert store.deleted == ["doc.pdf:h:0", "doc.pdf:h:0"]
