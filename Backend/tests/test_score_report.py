import importlib.util
from pathlib import Path

import openpyxl
import pandas as pd

from app.config import FAIL_MSG

_spec = importlib.util.spec_from_file_location(
    "score_report", Path(__file__).resolve().parents[2] / "eval" / "score_report.py")
score_report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(score_report)

COLUMNS = ["ID", "Question", "Expected Answer", "Expected Status", "Type", "Split", "Ref Doc",
           "Answer", "Sources", "Conflicts", "Cost ($)", "LLM Score", "LLM Reasoning"]


def _workbook(path, rows):
    """rows: (id, expected_status, type, split, answer, sources, llm_score)."""
    data = [{"ID": i, "Question": "q", "Expected Answer": "e", "Expected Status": st, "Type": t, "Split": sp,
             "Ref Doc": "-", "Answer": a, "Sources": s, "Conflicts": "", "Cost ($)": 0.001,
             "LLM Score": score, "LLM Reasoning": "r"} for i, st, t, sp, a, s, score in rows]
    pd.DataFrame(data, columns=COLUMNS).to_excel(path, sheet_name="Eval", index=False)
    return path


RUN1 = [
    ("EV-01", "answered", "answerable", "dev", "Yes. [Source: LC-POL-001.pdf (Page 1)]", "LC-POL-001.pdf", 90),
    ("EV-02", "answered", "deduction", "held_out", "No, per Velmora questionnaire.", "Velmora RFP.xlsx - Sheet", 40),
    ("EV-03", "not_found", "unanswerable", "dev", FAIL_MSG, "", 0),         # correct refusal, LLM Score ignored
    ("EV-04", "not_found", "unanswerable", "held_out", "We use AES.", "VSA-12", 100),  # wrong answer
    ("EV-05", "partial", "partial", "dev", "Standards-based SSO.", "LC-POL-002.pdf", 70),  # "ds-" inside a word: no leak
]


def test_single_run_scores_not_found_leaks_and_low_rows(tmp_path):
    rows = {r["id"]: r for r in score_report.load_run(_workbook(tmp_path / "Evaluated_a.xlsx", RUN1))}
    assert rows["EV-03"]["score"] == 100 and rows["EV-04"]["score"] == 0
    assert [i for i, r in rows.items() if r["leak_answer"]] == ["EV-02"]
    assert [i for i, r in rows.items() if r["leak_sources"]] == ["EV-02", "EV-04"]

    text = score_report.report([tmp_path / "Evaluated_a.xlsx"])
    assert "| Overall | 5 | 60.0 |" in text            # (90 + 40 + 100 + 0 + 70) / 5
    assert "| dev | 3 | 86.7 |" in text and "| held_out | 2 | 20.0 |" in text
    assert "| deduction | 0 | – | 1 | 40.0 |" in text
    assert "Unanswerable handled (not_found or needs_review): 1/2 (not_found 1, needs_review 0)" in text
    assert "Unflagged answers to unanswerable questions: 1: EV-04" in text
    assert "Answerable rows flagged needs_review: 0 (dev 0, held_out 0): –" in text
    assert "Wrongful refusals (answerable question answered with the fail text): 0 (dev 0, held_out 0): –" in text
    assert "| Answer | 1 | EV-02 |" in text and "| Sources | 2 | EV-02, EV-04 |" in text
    assert "| EV-02 | deduction | held_out | 40 |" in text and "| EV-04 | unanswerable | held_out | 0 |" in text
    assert "| EV-01 |" not in text


def test_name_only_inside_citation_is_sources_leak_not_text_leak(tmp_path):
    answer = "Yes, 24/7 support. [**Source: Velmora RFP.xlsx - Assessment (Row 16)**]"
    path = _workbook(tmp_path / "Evaluated_c.xlsx",
                     [("EV-14", "answered", "past_rfp_only", "dev", answer, "Velmora RFP.xlsx - Assessment", 90)])
    [row] = score_report.load_run(path)
    assert row["leak_answer"] is False and row["leak_sources"] is True


def test_several_runs_show_mean_min_max(tmp_path):
    run2 = [r[:6] + (s,) for r, s in zip(RUN1, [70, 80, 0, 100, 70])]
    run2[1] = run2[1][:4] + ("No.", "LC-POL-001.pdf", 80)  # no leak in run 2
    paths = [_workbook(tmp_path / "Evaluated_a.xlsx", RUN1), _workbook(tmp_path / "Evaluated_b.xlsx", run2)]
    text = score_report.report(paths)
    assert "| Overall | 5 | 62.0 (60.0–64.0) |" in text
    assert "| Answer | 0.5 (0–1) | EV-02 (1/2) |" in text
    assert "| EV-02 | deduction | held_out | 60.0 (40–80) |" in text


def test_report_prints_run_info_and_ignores_its_sheet(tmp_path):
    from app.excel_io import write_run_info
    path = _workbook(tmp_path / "Evaluated_a.xlsx", RUN1)
    wb = openpyxl.load_workbook(path)
    write_run_info(wb, {"Agent model": "gpt-6-luna", "Judge model": "gpt-6-luna", "Git commit": "abc1234"})
    wb.save(path)
    text = score_report.report([path, _workbook(tmp_path / "Evaluated_b.xlsx", RUN1)])
    assert "- Evaluated_a.xlsx (Agent model: gpt-6-luna; Judge model: gpt-6-luna; Git commit: abc1234)" in text
    assert "- Evaluated_b.xlsx (no run info)" in text
    assert "| Overall | 5 | 60.0 (60.0–60.0) |" in text  # Run info rows not counted


def test_wrongful_refusals_count_answerable_rows_with_fail_text_by_split(tmp_path):
    rows = RUN1 + [("EV-06", "answered", "answerable", "held_out", FAIL_MSG, "", 0),
                   ("EV-07", "partial", "partial", "dev", f"Partly. {FAIL_MSG}", "", 30)]
    text = score_report.report([_workbook(tmp_path / "Evaluated_w.xlsx", rows)])
    assert "Wrongful refusals (answerable question answered with the fail text): 2 (dev 1, held_out 1): EV-06, EV-07" in text


def test_status_column_counts_needs_review_as_handled_and_flags_answerable_rows(tmp_path):
    path = _workbook(tmp_path / "Evaluated_s.xlsx", RUN1)
    df = pd.read_excel(path)
    # EV-04 (unanswerable) paraphrased but flagged; EV-05 (answerable) flagged.
    df.insert(df.columns.get_loc("Answer") + 1, "Answer status",
              ["answered", "answered", "not_found", "needs_review", "needs_review"])
    df.to_excel(path, sheet_name="Eval", index=False)
    rows = {r["id"]: r for r in score_report.load_run(path)}
    assert rows["EV-04"]["score"] == 100 and rows["EV-04"]["status"] == "needs_review"
    text = score_report.report([path])
    assert "Unanswerable handled (not_found or needs_review): 2/2 (not_found 1, needs_review 1)" in text
    assert "Unflagged answers to unanswerable questions: 0: –" in text
    assert "Answerable rows flagged needs_review: 1 (dev 1, held_out 0): EV-05" in text


def test_status_inferred_from_review_note_in_older_files(tmp_path):
    path = _workbook(tmp_path / "Evaluated_o.xlsx", RUN1)
    df = pd.read_excel(path)
    df.insert(df.columns.get_loc("Conflicts") + 1, "Review note", ["", "", "", "Model text before not-found override: x", ""])
    df.to_excel(path, sheet_name="Eval", index=False)
    rows = {r["id"]: r for r in score_report.load_run(path)}
    assert [rows[i]["status"] for i in ("EV-01", "EV-03", "EV-04")] == ["answered", "not_found", "needs_review"]
