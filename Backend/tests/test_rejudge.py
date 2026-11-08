import importlib.util
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest
from openpyxl.styles import PatternFill

_spec = importlib.util.spec_from_file_location("rejudge", Path(__file__).resolve().parents[2] / "eval" / "rejudge.py")
rejudge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rejudge)

HEADER = ["ID", "Question", "Expected Answer", "Expected Status", "Answer", "Sources", "Cost ($)", "LLM Score", "LLM Reasoning"]


def _evaluated(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Eval"
    ws.append(HEADER)
    ws.append(["EV-01", "q1", "Yes.", "answered", "Yes, we do.", "a.pdf", 0.001, 100, "old"])
    ws.append(["EV-02", "q2", "", "answered", "Something.", "", 0.001, 0, ""])  # no expected: not judged
    ws.append(["EV-03", "q3", "No.", "answered", "Yes.", "b.pdf", 0.002, 90, "old"])
    ws["E2"].fill = PatternFill("solid", fgColor="FFFF00")
    wb.save(path)
    return path


def test_rejudge_overwrites_scores_only_and_sums_cost(tmp_path, monkeypatch):
    calls = []

    def fake_judge(question, answer, expected, judge_model=None):
        calls.append((question, answer, expected, judge_model))
        return SimpleNamespace(score=10 if expected == "No." else 80, reasoning=f"new {question}"), 0.25

    monkeypatch.setattr(rejudge, "run_llm_judge", fake_judge)
    path = _evaluated(tmp_path / "Evaluated_x.xlsx")

    out, total, n = rejudge.rejudge(str(path), "gpt-6-luna", workers=1)

    assert out == str(tmp_path / "Evaluated_x_rejudged_gpt-6-luna.xlsx")
    assert (n, total) == (2, 0.5)
    assert sorted(calls) == [("q1", "Yes, we do.", "Yes.", "gpt-6-luna"), ("q3", "Yes.", "No.", "gpt-6-luna")]
    ws = openpyxl.load_workbook(out)["Eval"]
    assert [c.value for c in ws[1]] == HEADER
    assert [[c.value for c in row] for row in ws.iter_rows(min_row=2)] == [
        ["EV-01", "q1", "Yes.", "answered", "Yes, we do.", "a.pdf", 0.001, 80, "new q1"],
        ["EV-02", "q2", None, "answered", "Something.", None, 0.001, 0, None],
        ["EV-03", "q3", "No.", "answered", "Yes.", "b.pdf", 0.002, 10, "new q3"],
    ]
    assert ws["E2"].fill.fgColor.rgb.endswith("FFFF00")  # formatting kept


def test_unknown_judge_model_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unknown judge model"):
        rejudge.rejudge(str(_evaluated(tmp_path / "Evaluated_x.xlsx")), "gpt-nope")
