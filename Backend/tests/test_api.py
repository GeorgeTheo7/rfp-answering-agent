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
