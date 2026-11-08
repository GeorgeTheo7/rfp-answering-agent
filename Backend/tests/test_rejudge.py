import importlib.util
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest
from openpyxl.styles import PatternFill

from app.excel_io import RUN_INFO_SHEET, read_run_info, write_run_info

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
    wb = openpyxl.load_workbook(out)
    ws = wb["Eval"]
    assert [c.value for c in ws[1]] == HEADER
    assert [[c.value for c in row] for row in ws.iter_rows(min_row=2)] == [
        ["EV-01", "q1", "Yes.", "answered", "Yes, we do.", "a.pdf", 0.001, 80, "new q1"],
        ["EV-02", "q2", None, "answered", "Something.", None, 0.001, 0, None],
        ["EV-03", "q3", "No.", "answered", "Yes.", "b.pdf", 0.002, 10, "new q3"],
    ]
    assert ws["E2"].fill.fgColor.rgb.endswith("FFFF00")  # formatting kept
    info = read_run_info(wb)  # old file without Run info: agent fields unknown
    assert (info["Agent model"], info["Timestamp"], info["Judge model"]) == ("unknown", "unknown", "gpt-6-luna")
    assert info["Judge settings"] == '{"reasoning_effort": "low"}' and info["Rejudged at"] and info["Rejudge commit"]


def test_unknown_judge_model_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unknown judge model"):
        rejudge.rejudge(str(_evaluated(tmp_path / "Evaluated_x.xlsx")), "gpt-nope")


def test_rejudge_keeps_agent_run_info_and_replaces_judge_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(rejudge, "run_llm_judge", lambda q, a, e, judge_model=None: (SimpleNamespace(score=1, reasoning="r"), 0.0))
    path = _evaluated(tmp_path / "Evaluated_x.xlsx")
    wb = openpyxl.load_workbook(path)
    write_run_info(wb, {"Agent model": "gpt-4o-mini", "Judge model": "gpt-4o-mini-2024-07-18",
                        "Judge settings": '{"temperature": 0}', "Timestamp": "2026-11-08T06:00:00+02:00", "Git commit": "abc1234"})
    wb.save(path)

    out, _, n = rejudge.rejudge(str(path), "gpt-6-luna", workers=1)

    assert n == 2  # the Run info sheet is not judged
    wb = openpyxl.load_workbook(out)
    info = read_run_info(wb)
    assert {k: info[k] for k in ("Agent model", "Timestamp", "Git commit")} == {
        "Agent model": "gpt-4o-mini", "Timestamp": "2026-11-08T06:00:00+02:00", "Git commit": "abc1234"}
    assert (info["Judge model"], info["Judge settings"]) == ("gpt-6-luna", '{"reasoning_effort": "low"}')
    assert wb.sheetnames == ["Eval", RUN_INFO_SHEET]
