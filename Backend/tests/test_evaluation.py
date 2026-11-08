from contextlib import contextmanager
from types import SimpleNamespace

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app import api, evaluation
from app.config import JUDGE_MODEL
from app.main import app


def test_judge_uses_pinned_model_at_temperature_0_and_prices_it(monkeypatch):
    seen = {}

    def fake_chat(**kwargs):
        seen.update(kwargs)
        result = evaluation.JudgeOutput(reasoning="ok", generated_verdict="no", score=80)
        return SimpleNamespace(with_structured_output=lambda schema: seen.update(schema=schema) or SimpleNamespace(
            invoke=lambda prompt: result))

    @contextmanager
    def fake_callback():
        yield SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=1_000_000, total_cost=99.0)

    monkeypatch.setattr(evaluation, "ChatOpenAI", fake_chat)
    monkeypatch.setattr(evaluation, "get_openai_callback", fake_callback)

    result, cost = evaluation.run_llm_judge("q", "generated", "Yes, within 6 months.")

    assert (seen["model"], seen["temperature"]) == (JUDGE_MODEL, 0)
    assert seen["schema"] is evaluation.JudgeOutput
    assert result.score == 20  # verdict "no" vs expected "Yes": capped
    assert cost == 0.15 + 0.60  # MODEL_PRICING, not the callback's total_cost


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


@pytest.mark.parametrize("expected,verdict", [
    ("Yes. Data is deleted within about 125 days, which is within 6 months.", "yes"),
    ("no, not yet.", "no"),
    ("**Yes** - certified.", "yes"),
    ("Not stated in the documents.", None),     # "Not" is not the word "No"
    ("Yesterday's backup.", None),
    ("It depends on the role.", None),
    ("", None),
])
def test_expected_verdict(expected, verdict):
    assert evaluation.expected_verdict(expected) == verdict


def _judged(verdict, score, expected):
    return evaluation.apply_verdict_cap(evaluation.JudgeOutput(reasoning="r", generated_verdict=verdict, score=score), expected)


@pytest.mark.parametrize("verdict,expected", [("no", "Yes. Within 6 months."), ("yes", "No, not yet.")])
def test_opposite_verdict_caps_score_at_20_and_says_why(verdict, expected):
    result = _judged(verdict, 80, expected)
    assert result.score == 20 and "Capped at 20" in result.reasoning


@pytest.mark.parametrize("verdict,score,expected", [
    ("yes", 80, "Yes. Within 6 months."),          # agrees
    ("neither", 80, "Yes. Within 6 months."),      # neither never caps
    ("no", 80, "It depends on the role."),         # expected has no verdict
    ("no", 10, "Yes. Within 6 months."),           # already below the cap
])
def test_no_cap(verdict, score, expected):
    result = _judged(verdict, score, expected)
    assert result.score == score and result.reasoning == "r"
