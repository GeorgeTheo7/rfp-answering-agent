from contextlib import contextmanager
from types import SimpleNamespace

import openpyxl
from fastapi.testclient import TestClient

from app import api, evaluation
from app.config import JUDGE_MODEL
from app.main import app


def test_judge_uses_pinned_model_at_temperature_0_and_prices_it(monkeypatch):
    seen = {}

    def fake_chat(**kwargs):
        seen.update(kwargs)
        result = evaluation.EvaluationResult(score=80, reasoning="ok")
        return SimpleNamespace(with_structured_output=lambda schema: SimpleNamespace(invoke=lambda prompt: result))

    @contextmanager
    def fake_callback():
        yield SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=1_000_000, total_cost=99.0)

    monkeypatch.setattr(evaluation, "ChatOpenAI", fake_chat)
    monkeypatch.setattr(evaluation, "get_openai_callback", fake_callback)

    result, cost = evaluation.run_llm_judge("q", "generated", "expected")

    assert (seen["model"], seen["temperature"]) == (JUDGE_MODEL, 0)
    assert result.score == 80 and cost == 0.15 + 0.60  # MODEL_PRICING, not the callback's total_cost


def test_evaluate_runs_agent_with_uploaded_model_and_judge_without_it(tmp_path, monkeypatch):
    wb = openpyxl.Workbook()
    wb.active.append(["Question", "Expected Answer"])
    wb.active.append(["q", "yes"])
    path = tmp_path / "eval.xlsx"
    wb.save(path)

    graph_inputs, judge_args = [], []
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(api, "rfp_graph", SimpleNamespace(
        invoke=lambda state, **k: graph_inputs.append(state) or {"final_answers": []}))
    monkeypatch.setattr(api, "run_llm_judge", lambda *args, **kwargs: judge_args.append((args, kwargs)) or (
        SimpleNamespace(score=100, reasoning="r"), 0.0))

    with open(path, "rb") as f:
        response = TestClient(app).post("/api/rfp/evaluate", files={"file": ("eval.xlsx", f)},
                                        data={"model": "gpt-5-mini"})

    assert response.status_code == 200
    assert graph_inputs[0]["selected_model"] == "gpt-5-mini"
    assert len(judge_args) == 1 and judge_args[0][1] == {} and len(judge_args[0][0]) == 3
