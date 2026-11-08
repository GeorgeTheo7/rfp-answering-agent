import base64
import json
import io
import re
from contextlib import contextmanager
from types import SimpleNamespace

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app import api, evaluation
from app.agent import nodes
from app.config import JUDGE_MODEL, MODEL_PRICING, MODEL_SETTINGS
from app.excel_io import RUN_INFO_SHEET, read_run_info
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

    monkeypatch.setattr(evaluation, "JUDGE_MODEL", "gpt-4o-mini-2024-07-18")
    monkeypatch.setattr(nodes, "ChatOpenAI", fake_chat)
    monkeypatch.setattr(evaluation, "get_openai_callback", fake_callback)

    result, cost = evaluation.run_llm_judge("q", "generated", "Yes, within 6 months.")

    assert (seen["model"], seen["temperature"]) == ("gpt-4o-mini-2024-07-18", 0)
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
    wb = openpyxl.load_workbook(io.BytesIO(base64.b64decode(response.json()["excel_base64"])))
    assert wb.sheetnames[-1] == RUN_INFO_SHEET and wb.sheetnames[0] != RUN_INFO_SHEET
    info = read_run_info(wb)
    assert list(info) == ["Agent model", "Judge model", "Judge settings", "Timestamp", "Git commit",
                          "Backend started"]
    assert (info["Agent model"], info["Judge model"]) == ("gpt-5-mini", JUDGE_MODEL)
    assert (info["Git commit"], info["Backend started"]) == (evaluation.CODE_COMMIT, evaluation.BACKEND_STARTED)
    assert info["Judge settings"] == json.dumps(MODEL_SETTINGS[JUDGE_MODEL])
    assert re.match(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", info["Timestamp"]) and info["Git commit"]


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
    assert result.score == 20
    assert result.reasoning == f"r [verdict: {verdict}] [Capped at 20: expected '{'yes' if verdict == 'no' else 'no'}', generated '{verdict}'.]"


@pytest.mark.parametrize("verdict,score,expected", [
    ("yes", 80, "Yes. Within 6 months."),          # agrees
    ("neither", 80, "Yes. Within 6 months."),      # neither never caps
    ("no", 80, "It depends on the role."),         # expected has no verdict
    ("no", 10, "Yes. Within 6 months."),           # already below the cap
])
def test_no_cap(verdict, score, expected):
    result = _judged(verdict, score, expected)
    assert result.score == score and result.reasoning == f"r [verdict: {verdict}]"


def test_every_judge_model_is_priced_and_the_default_is_configured():
    assert JUDGE_MODEL == "gpt-6-luna" and JUDGE_MODEL in MODEL_SETTINGS
    assert all(model in MODEL_PRICING for model in MODEL_SETTINGS)


def test_switching_judge_to_gpt_6_luna_uses_its_settings_and_price(monkeypatch):
    seen = {}

    def fake_chat(**kwargs):
        seen.update(kwargs)
        result = evaluation.JudgeOutput(reasoning="ok", generated_verdict="yes", score=90)
        return SimpleNamespace(with_structured_output=lambda schema: SimpleNamespace(invoke=lambda prompt: result))

    @contextmanager
    def fake_callback():
        yield SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=1_000_000, total_cost=99.0)

    monkeypatch.setattr(evaluation, "JUDGE_MODEL", "gpt-6-luna")
    monkeypatch.setattr(nodes, "ChatOpenAI", fake_chat)
    monkeypatch.setattr(evaluation, "get_openai_callback", fake_callback)

    result, cost = evaluation.run_llm_judge("q", "generated", "Yes.")

    assert seen["model"] == "gpt-6-luna" and seen["reasoning_effort"] == "low" and "temperature" not in seen
    assert result.score == 90 and result.reasoning == "ok [verdict: yes]"
    assert cost == 0.10 + 0.50


def test_git_commit_is_short_hash_or_unknown(monkeypatch):
    assert re.fullmatch(r"[0-9a-f]{7,}(\+dirty)?|unknown", evaluation.git_commit())

    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(evaluation.subprocess, "run", no_git)
    assert evaluation.git_commit() == "unknown"


def test_run_info_records_commit_and_start_time_read_at_import_not_per_request(monkeypatch):
    monkeypatch.setattr(evaluation, "CODE_COMMIT", "loaded1")
    monkeypatch.setattr(evaluation, "BACKEND_STARTED", "2026-11-08T04:36:35+02:00")
    monkeypatch.setattr(evaluation, "git_commit", lambda: "head999")  # HEAD moved on since the backend started
    info = evaluation.run_info("gpt-4o-mini")
    assert (info["Git commit"], info["Backend started"]) == ("loaded1", "2026-11-08T04:36:35+02:00")
    assert info["Timestamp"] != info["Backend started"]
