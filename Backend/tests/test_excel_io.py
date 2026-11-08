import base64
import io
from types import SimpleNamespace

import openpyxl
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from openpyxl.worksheet.datavalidation import DataValidation

from app import api
from app.agent import graph as graph_module
from app.agent import nodes
from app.agent.nodes import extract_questions_node, generate_final_report_node, is_fail_text
from app.agent.schemas import Answer, ExtractedQuestion, Question, RFPQuestions, Status, company_analysts
from app.config import FAIL_MSG, FAIL_MSG_PREFIX, OLD_FAIL_MSG_PREFIX
from app.excel_io import (
    build_answer_sheets, create_formatted_excel_bytes, detect_status_columns, find_id_column,
    find_question_column, parse_question_id,
)
from app.main import app


def _save(wb, tmp_path, name="rfp.xlsx"):
    path = str(tmp_path / name)
    wb.save(path)
    return path


# --- parse_question_id ---

def test_parse_id_with_sheet():
    assert parse_question_id("[Sheet1] 3") == ("Sheet1", "3")


def test_parse_id_sheet_name_with_spaces():
    assert parse_question_id("[My Sheet] A.1") == ("My Sheet", "A.1")


def test_parse_id_without_brackets_uses_default_sheet():
    assert parse_question_id("Q7") == ("RFP Responses", "Q7")


# --- detect_status_columns ---

def test_detect_inline_dropdown(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "RFP"
    ws.append(["ID", "Question", "Supported"])
    ws.append(["1", "Do you encrypt data?", None])
    dv = DataValidation(type="list", formula1='"Yes,No,Partial"')
    ws.add_data_validation(dv)
    dv.add("C2:C10")

    result = detect_status_columns(_save(wb, tmp_path))

    assert result == {"RFP": [{"column": "Supported", "allowed_values": ["Yes", "No", "Partial"]}]}


def test_detect_range_reference_dropdown(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "RFP"
    ws.append(["ID", "Question", "Compliance"])
    lists = wb.create_sheet("Lists")
    for v in ["Full", "Partial", "None"]:
        lists.append([v])
    dv = DataValidation(type="list", formula1="Lists!$A$1:$A$3")
    ws.add_data_validation(dv)
    dv.add("C2:C10")

    result = detect_status_columns(_save(wb, tmp_path))

    assert result == {"RFP": [{"column": "Compliance", "allowed_values": ["Full", "Partial", "None"]}]}


def test_detect_skips_non_xlsx():
    assert detect_status_columns("old_format.xls") == {}


# --- find_id_column ---

@pytest.mark.parametrize("header", [
    "ID", "id", " question  id ", "Question_ID", "Ref", "Ref No.", "Reference No", "No", "No.", "#", "Α/Α", "α/α",
])
def test_find_id_column_matches(header):
    assert find_id_column(["Question", header, "Answer"]) == header


@pytest.mark.parametrize("header", [
    "Supported (Yes/No)", "Provider", "Guidance", "Notes", "Reference", "Valid", "Answer ID Notes",
])
def test_find_id_column_ignores_lookalikes(header):
    assert find_id_column(["Question", header, "Answer"]) is None


def test_find_id_column_priority_not_column_order():
    assert find_id_column(["No", "Question", "ID"]) == "ID"


def test_find_id_column_tick_box_no_is_not_an_id():
    assert find_id_column(["Question", "Yes", "No"]) is None


def test_find_id_column_keeps_original_header():
    assert find_id_column(["Question", "  Q No. "]) == "  Q No. "


def test_find_id_column_non_string_headers():
    assert find_id_column([1, 2.5, None]) is None


# --- find_question_column ---

@pytest.mark.parametrize("columns,expected", [
    (["Question ID", "Question"], "Question"),
    (["ID", "Question No.", "Security Question"], "Security Question"),
    (["α/α", "Ερώτηση"], "Ερώτηση"),
    (["Question ID", "Answer"], None),
    (["Requirement", "Notes"], None),
])
def test_find_question_column(columns, expected):
    assert find_question_column(columns) == expected


def _extract_texts(wb, tmp_path):
    return [q.text for q in extract_questions_node({"rfp_input_path": _save(wb, tmp_path)})["extracted_questions"]]


def test_extract_does_not_read_question_id_as_question(tmp_path):
    wb = openpyxl.Workbook()
    wb.active.append(["Question ID", "Question"])
    wb.active.append(["A1", "Do you encrypt data?"])

    assert _extract_texts(wb, tmp_path) == ["Do you encrypt data?"]


def test_extract_fallback_skips_id_column(tmp_path):
    wb = openpyxl.Workbook()
    wb.active.append(["ID", "Requirement"])
    wb.active.append(["A1", "Encrypt data at rest"])

    assert _extract_texts(wb, tmp_path) == ["Encrypt data at rest"]


def test_extract_skips_sheet_with_only_an_id_column(tmp_path):
    wb = openpyxl.Workbook()
    wb.active.append(["ID"])
    wb.active.append(["A1"])

    assert _extract_texts(wb, tmp_path) == []


def test_pdf_preview_and_excel_from_answers(monkeypatch):
    answers = [Answer(question_id="Q1", question_text="Do you encrypt data?", assigned_analyst="CISO",
                      answer_text="Yes", sources_used=[], category="Security", cost=0.001)]
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(api, "rfp_graph", SimpleNamespace(invoke=lambda *a, **k: {"final_answers": answers}))

    response = TestClient(app).post("/api/rfp/analyze", files={"file": ("rfp.pdf", b"unused")})

    assert response.status_code == 200
    row = response.json()["preview_data"][0]
    assert (row["id"], row["question"], row["category"]) == ("Q1", "Do you encrypt data?", "Security")
    ws = openpyxl.load_workbook(io.BytesIO(base64.b64decode(response.json()["excel_base64"])))["RFP Responses"]
    assert [c.value for c in ws[1]] == ["Question ID", "Category", "Question", "Answer", "Sources", "Conflicts", "Cost ($)"]
    assert ws["B2"].value == "CISO"  # the PDF sheet shows the analyst as category


@pytest.mark.parametrize("note", ["", "Judge: unsupported"])
def test_review_note_column_only_when_some_answer_has_a_note(tmp_path, note):
    wb = openpyxl.Workbook()
    wb.active.title = "RFP"
    wb.active.append(["ID", "Question"])
    wb.active.append(["A1", "q1"])
    wb.active.append(["A2", "q2"])
    answers = [Answer(question_id=f"[RFP] A{i + 1}", question_text=f"q{i + 1}", assigned_analyst="a", answer_text="x",
                      sheet="RFP", row_index=i, review_note=note if i == 0 else "") for i in range(2)]

    df = build_answer_sheets(_save(wb, tmp_path), answers)["RFP"]

    if note:
        assert list(df.columns) == ["ID", "Question", "Answer", "Sources", "Conflicts", "Review note", "Cost ($)"]
        assert list(df["Review note"]) == [note, ""]
    else:
        assert "Review note" not in df.columns


# --- ID column detection in the graph nodes ---

def test_id_column_not_confused_with_yes_no_header(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "RFP"
    # "Supported (Yes/No)" must come before "ID" to trigger the bug
    ws.append(["Question", "Supported (Yes/No)", "ID"])
    ws.append(["Do you encrypt data?", "Yes", "A1"])
    ws.append(["Do you have MFA?", "Yes", "A2"])

    result = extract_questions_node({"rfp_input_path": _save(wb, tmp_path)})

    assert [q.id for q in result["extracted_questions"]] == ["[RFP] A1", "[RFP] A2"]


def _answer_of(q, **kwargs):
    return Answer(question_id=q.id, question_text=q.text, assigned_analyst=q.category,
                  answer_text=f"answer to {q.text}", sources_used=[],
                  category=q.category, sheet=q.sheet, row_index=q.row_index, **kwargs)


def _answer_all(path):
    """Extract, then one distinct answer per question (no LLM involved)."""
    questions = extract_questions_node({"rfp_input_path": path})["extracted_questions"]
    return questions, [_answer_of(q) for q in questions]


def test_duplicate_ids_fall_back_to_row_ids_and_keep_every_answer(tmp_path, capsys):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "RFP"
    ws.append(["ID", "Question"])
    ws.append(["A1", "first"])
    ws.append(["A1", "second"])

    path = _save(wb, tmp_path)
    questions, answers = _answer_all(path)

    assert [q.id for q in questions] == ["[RFP] Q1", "[RFP] Q2"]
    assert build_answer_sheets(path, answers)["RFP"]["Answer"].tolist() == ["answer to first", "answer to second"]
    assert "duplicate IDs" in capsys.readouterr().out


def test_id_colliding_with_row_id_falls_back(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "RFP"
    ws.append(["ID", "Question"])
    ws.append(["Q2", "first"])
    ws.append([None, "second"])  # would get row ID Q2

    path = _save(wb, tmp_path)
    questions, answers = _answer_all(path)

    assert [q.id for q in questions] == ["[RFP] Q1", "[RFP] Q2"]
    assert build_answer_sheets(path, answers)["RFP"]["Answer"].tolist() == ["answer to first", "answer to second"]


def test_blank_ids_are_not_duplicates(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "RFP"
    ws.append(["ID", "Question"])
    ws.append(["A1", "first"])
    ws.append([None, "second"])
    ws.append([None, "third"])

    questions, _ = _answer_all(_save(wb, tmp_path))

    assert [q.id for q in questions] == ["[RFP] A1", "[RFP] Q2", "[RFP] Q3"]


def test_duplicates_only_affect_their_own_sheet(tmp_path):
    wb = openpyxl.Workbook()
    dup = wb.active
    dup.title = "Dup"
    dup.append(["ID", "Question"])
    dup.append(["A1", "first"])
    dup.append(["A1", "second"])
    ok = wb.create_sheet("Ok")
    ok.append(["ID", "Question"])
    ok.append(["A1", "third"])

    questions, _ = _answer_all(_save(wb, tmp_path))

    assert [q.id for q in questions] == ["[Dup] Q1", "[Dup] Q2", "[Ok] A1"]


# --- Sheet names: report node -> preview -> export_edits ---

def _two_sheet_workbook():
    wb = openpyxl.Workbook()
    security = wb.active
    security.title = "Security"
    security.append(["ID", "Question"])
    security.append(["SEC-01", "first"])
    security.append(["SEC-02", "second"])
    general = wb.create_sheet("General")
    general.append(["Requirement"])  # no ID column, no "question" header
    general.append(["third"])
    return wb


def _analyze(path, answers, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(api, "rfp_graph", SimpleNamespace(invoke=lambda *a, **k: {"final_answers": answers}))
    with open(path, "rb") as f:
        response = TestClient(app).post("/api/rfp/analyze", files={"file": ("rfp.xlsx", f)})
    assert response.status_code == 200
    return response.json()


def test_preview_ids_match_the_question_ids(tmp_path, monkeypatch):
    path = _save(_two_sheet_workbook(), tmp_path)
    questions, answers = _answer_all(path)

    rows = _analyze(path, answers, monkeypatch)["preview_data"]

    assert [q.id for q in questions] == ["[Security] SEC-01", "[Security] SEC-02", "[General] Q1"]
    assert [row["id"] for row in rows] == [q.id for q in questions]


def test_export_edits_keeps_original_sheets(tmp_path, monkeypatch):
    path = _save(_two_sheet_workbook(), tmp_path)
    _, answers = _answer_all(path)
    rows = _analyze(path, answers, monkeypatch)["preview_data"]

    response = TestClient(app).post("/api/rfp/export_edits", json={"rows": rows, "filename": "out.xlsx"})

    assert response.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(response.content))
    assert wb.sheetnames == ["Security", "General"]
    assert [c.value for c in wb["Security"]["A"]] == ["ID", "SEC-01", "SEC-02"]
    assert [c.value for c in wb["General"]["A"]] == ["ID", "Q1"]


def test_analyze_excel_has_no_internal_columns(tmp_path, monkeypatch):
    path = _save(_two_sheet_workbook(), tmp_path)
    _, answers = _answer_all(path)

    body = _analyze(path, answers, monkeypatch)

    wb = openpyxl.load_workbook(io.BytesIO(base64.b64decode(body["excel_base64"])))
    for ws in wb.worksheets:
        assert not [c.value for c in ws[1] if str(c.value).startswith("_")]


# --- Answers -> rows ---

def _workbook_with_blank_rows():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "RFP"
    ws.append(["ID", "Question", "Category"])
    ws.append(["A1", "first", "Tech"])
    ws.append(["A2", None, None])
    ws.append(["A3", None, None])
    ws.append(["A4", "second", "Security"])
    return wb


def test_blank_rows_each_answer_lands_in_its_own_row(tmp_path):
    path = _save(_workbook_with_blank_rows(), tmp_path)

    questions, answers = _answer_all(path)
    df = build_answer_sheets(path, answers)["RFP"]

    assert [q.row_index for q in questions] == [0, 3]
    assert df["ID"].tolist() == ["A1", "A2", "A3", "A4"]
    assert df["Answer"].tolist() == ["answer to first", "", "", "answer to second"]


def test_preview_category_not_shifted_by_blank_rows(tmp_path, monkeypatch):
    path = _save(_workbook_with_blank_rows(), tmp_path)
    _, answers = _answer_all(path)

    rows = _analyze(path, answers, monkeypatch)["preview_data"]

    assert [(r["id"], r["category"]) for r in rows] == [("[RFP] A1", "Tech"), ("[RFP] A4", "Security")]


def test_preview_question_not_blank_when_sheets_have_different_headers(tmp_path, monkeypatch):
    path = _save(_two_sheet_workbook(), tmp_path)  # "General" uses "Requirement", not "Question"
    _, answers = _answer_all(path)

    rows = _analyze(path, answers, monkeypatch)["preview_data"]

    assert [r["question"] for r in rows] == ["first", "second", "third"]


def test_preview_answer_not_taken_from_expected_answer_column(tmp_path, monkeypatch):
    wb = openpyxl.Workbook()
    wb.active.append(["Question", "Expected Answer"])
    wb.active.append(["first", "the expected one"])
    path = _save(wb, tmp_path)
    _, answers = _answer_all(path)

    rows = _analyze(path, answers, monkeypatch)["preview_data"]

    assert rows[0]["answer"] == "answer to first"


def test_blank_cost_in_existing_column_does_not_break_analyze(tmp_path, monkeypatch):
    wb = openpyxl.Workbook()
    wb.active.append(["Question", "Cost ($)"])
    wb.active.append(["first", 1.0])
    wb.active.append([None, None])
    path = _save(wb, tmp_path)
    _, answers = _answer_all(path)

    assert [r["answer"] for r in _analyze(path, answers, monkeypatch)["preview_data"]] == ["answer to first"]


def test_dropdown_values_written_to_their_column_and_preview(tmp_path, monkeypatch):
    wb = openpyxl.Workbook()
    wb.active.title = "RFP"
    wb.active.append(["Question", "Supported"])
    wb.active.append(["first", None])
    path = _save(wb, tmp_path)
    questions = extract_questions_node({"rfp_input_path": path})["extracted_questions"]
    answers = [_answer_of(questions[0], status_values_json='{"supported": "Yes"}')]

    body = _analyze(path, answers, monkeypatch)

    assert body["preview_data"][0]["status_values"] == {"supported": "Yes"}
    assert build_answer_sheets(path, answers)["RFP"]["Supported"].tolist() == ["Yes"]


def test_report_sorts_excel_by_extraction_order_pdf_by_id(tmp_path):
    path = _save(_two_sheet_workbook(), tmp_path)
    questions, answers = _answer_all(path)

    excel = generate_final_report_node({"rfp_input_path": path, "extracted_questions": questions,
                                        "completed_answers": list(reversed(answers))})
    pdf_answers = [Answer(question_id=i, question_text="", assigned_analyst="", answer_text="", sources_used=[])
                   for i in ["Q2", "Q10", "Q1"]]
    pdf = generate_final_report_node({"rfp_input_path": "rfp.pdf", "completed_answers": pdf_answers})

    assert [a.question_id for a in excel["final_answers"]] == [q.id for q in questions]
    assert [a.question_id for a in pdf["final_answers"]] == ["Q1", "Q10", "Q2"]


def test_failed_question_keeps_its_row_and_category(monkeypatch):
    def fail(state):
        raise RuntimeError("boom")
    monkeypatch.setattr(graph_module, "question_graph", SimpleNamespace(invoke=fail))
    question = Question(id="[RFP] A1", text="q", category="Tech", sheet="RFP", row_index=4)

    answer = graph_module.answer_question_node({"question": question, "selected_model": "m"})["completed_answers"][0]

    assert (answer.category, answer.sheet, answer.row_index) == ("Tech", "RFP", 4)
    assert "SYSTEM ERROR" in answer.answer_text
    assert answer.status == Status.error


def test_pdf_extraction_builds_questions_without_location(monkeypatch):
    class FakeLLM:
        def __init__(self, **kwargs): pass
        def with_structured_output(self, schema): return self
        def invoke(self, prompt):
            return RFPQuestions(questions=[ExtractedQuestion(id="Q1", text="q", category="Tech")])
    monkeypatch.setattr(nodes, "ChatOpenAI", FakeLLM)
    monkeypatch.setattr(nodes, "PyMuPDFLoader", lambda path: SimpleNamespace(load=lambda: []))

    question = extract_questions_node({"rfp_input_path": "rfp.pdf"})["extracted_questions"][0]

    assert isinstance(question, Question)
    assert (question.id, question.text, question.category) == ("Q1", "q", "Tech")
    assert (question.sheet, question.row_index, question.status_specs) == (None, None, [])


# --- Status ---

RED, YELLOW = "00FFC7CE", "00FFEB9C"
OLD_FAIL_MSG = FAIL_MSG.replace(FAIL_MSG_PREFIX, OLD_FAIL_MSG_PREFIX)


def _fill(cell):
    return cell.fill.fgColor.rgb if cell.fill.fill_type else None


def _answer_fills(excel_file, sheet=None):
    wb = openpyxl.load_workbook(excel_file)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    col = [c.value for c in ws[1]].index("Answer")
    return [_fill(row[col]) for row in ws.iter_rows(min_row=2)]


@pytest.mark.parametrize("text,expected", [
    (FAIL_MSG, True),
    (FAIL_MSG_PREFIX + ".", True),  # near-miss: no ending
    (f"Partly known. {FAIL_MSG}", True),
    (OLD_FAIL_MSG, True),
    (OLD_FAIL_MSG_PREFIX + ".", True),
    ("We encrypt data [**Source: a.pdf (Page 1)**]", False),
    ("", False),
    (None, False),
])
def test_is_fail_text(text, expected):
    assert is_fail_text(text) is expected


def test_fail_msg_wording():
    assert FAIL_MSG == "I couldn't find a corresponding answer. Please provide a human to answer the question!"


def test_evaluator_excludes_expected_not_found_rows_in_old_and_new_wording(tmp_path, monkeypatch):
    wb = openpyxl.Workbook()
    wb.active.append(["Question", "Expected Answer"])
    wb.active.append(["real", "yes"])
    wb.active.append(["old full", OLD_FAIL_MSG])
    wb.active.append(["old prefix", OLD_FAIL_MSG_PREFIX])
    wb.active.append(["new full", FAIL_MSG])
    path = _save(wb, tmp_path, "rfp.xlsm")
    _, answers = _answer_all(path)
    # Only the real row scores 100: any not-found row counted would pull accuracy below 100.
    monkeypatch.setattr(api, "run_llm_judge", lambda q, g, expected: (
        SimpleNamespace(score=100 if expected == "yes" else 0, reasoning="r"), 0.0))

    body = _post_with_answers("/api/rfp/evaluate", path, answers, monkeypatch).json()

    assert body["overall_accuracy"] == 100
    assert len(body["results"]) == 4


@pytest.mark.parametrize("text,expected", [(FAIL_MSG, Status.not_found), (FAIL_MSG_PREFIX + ".", Status.not_found), ("yes", Status.answered)])
def test_finalize_sets_status_from_the_text_not_from_the_llm(text, expected):
    question = Question(id="[RFP] A1", text="q", category="Tech", sheet="RFP", row_index=0)
    draft = Answer(question_id="x", question_text="x", assigned_analyst="x", answer_text=text, sources_used=[],
                   status=Status.needs_review)

    answer = nodes.finalize_node({"question": question, "draft": draft, "analyst": company_analysts["Tech"],
                                  "conflicts": "", "status_map": {}, "allowed_sources": []})["answer"]

    assert answer.status == expected


@pytest.mark.parametrize("text,status,note", [
    (f"We encrypt data [**Source: a.pdf (Page 1)**]. Key rotation: {FAIL_MSG}", Status.needs_review, nodes.PARTIAL_NOTE),
    (f"{FAIL_MSG_PREFIX} for rotation. Data is encrypted.", Status.needs_review, nodes.PARTIAL_NOTE),
    (f"  {FAIL_MSG}  ", Status.not_found, ""),
    (OLD_FAIL_MSG, Status.not_found, ""),
    (FAIL_MSG_PREFIX + " in the documents.", Status.not_found, ""),
])
def test_finalize_flags_partial_not_found_answers_for_review(text, status, note):
    draft = Answer(question_id="x", question_text="x", assigned_analyst="x", answer_text=text, sources_used=[])

    answer = nodes.finalize_node({"draft": draft, "conflicts": "", "status_map": {}, "allowed_sources": []})["answer"]

    assert (answer.status, answer.review_note) == (status, note)


def test_finalize_keeps_existing_review_note_on_partial_answer():
    draft = Answer(question_id="x", question_text="x", assigned_analyst="x", answer_text=f"Yes. {FAIL_MSG}",
                   sources_used=[], review_note="Judge: weak")

    answer = nodes.finalize_node({"draft": draft, "conflicts": "", "status_map": {}, "allowed_sources": []})["answer"]

    assert answer.review_note == f"Judge: weak\n{nodes.PARTIAL_NOTE}"


@pytest.mark.parametrize("status,fill", [
    (Status.answered, None), (Status.not_found, RED), (Status.error, RED), (Status.needs_review, YELLOW), (None, None),
])
def test_writer_colours_answer_by_status(status, fill):
    df = pd.DataFrame({"Question": ["q"], "Answer": ["a"]})

    excel = create_formatted_excel_bytes(sheets_dict={"RFP": df}, statuses={"RFP": [status]})

    assert _answer_fills(excel) == [fill]


def test_writer_ignores_the_text_and_colours_only_the_exact_answer_column():
    df = pd.DataFrame({"Expected Answer": [FAIL_MSG, "e"], "Answer": [FAIL_MSG, "a"]})

    excel = create_formatted_excel_bytes(sheets_dict={"RFP": df}, statuses={"RFP": [Status.answered, Status.not_found]})

    ws = openpyxl.load_workbook(excel)["RFP"]
    assert [[_fill(c) for c in row] for row in ws.iter_rows(min_row=2)] == [[None, None], [None, RED]]


def test_analyze_sends_status_and_colours_each_row(tmp_path, monkeypatch):
    path = _save(_two_sheet_workbook(), tmp_path)
    questions, answers = _answer_all(path)
    answers[1].status = Status.not_found
    answers[2].status = Status.error

    body = _analyze(path, answers, monkeypatch)

    assert [r["status"] for r in body["preview_data"]] == ["answered", "not_found", "error"]
    excel = base64.b64decode(body["excel_base64"])
    assert _answer_fills(io.BytesIO(excel), "Security") == [None, RED]
    assert _answer_fills(io.BytesIO(excel), "General") == [RED]


def test_unanswered_row_with_old_fail_text_is_not_coloured(tmp_path, monkeypatch):
    wb = openpyxl.Workbook()
    wb.active.append(["Question", "Answer"])
    wb.active.append(["first", None])
    wb.active.append([None, FAIL_MSG])
    path = _save(wb, tmp_path)
    _, answers = _answer_all(path)

    body = _analyze(path, answers, monkeypatch)

    assert _answer_fills(io.BytesIO(base64.b64decode(body["excel_base64"]))) == [None, None]


def test_pdf_excel_colours_by_status(monkeypatch):
    answers = [Answer(question_id="Q1", question_text="q", assigned_analyst="a", answer_text=FAIL_MSG,
                      sources_used=[], status=Status.not_found)]
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(api, "rfp_graph", SimpleNamespace(invoke=lambda *a, **k: {"final_answers": answers}))

    body = TestClient(app).post("/api/rfp/analyze", files={"file": ("rfp.pdf", b"unused")}).json()

    assert _answer_fills(io.BytesIO(base64.b64decode(body["excel_base64"]))) == [RED]


def _export_row(**kwargs):
    return {"id": "[RFP] A1", "category": "Tech", "question": "q", "answer": "a", "sources": [],
            "conflicts": "", "cost": 0.0, **kwargs}


def test_export_edits_colours_by_status_per_sheet():
    rows = [_export_row(id="[One] A1", status="answered"), _export_row(id="[Two] B1", status="not_found"),
            _export_row(id="[One] A2", status="needs_review")]

    response = TestClient(app).post("/api/rfp/export_edits", json={"rows": rows, "filename": "out.xlsx"})

    assert _answer_fills(io.BytesIO(response.content), "One") == [None, YELLOW]
    assert _answer_fills(io.BytesIO(response.content), "Two") == [RED]


def test_export_edits_row_edited_by_a_human_is_not_red():
    # The frontend sends status "answered" after an edit, whatever the text says.
    rows = [_export_row(answer=FAIL_MSG, status="answered")]

    response = TestClient(app).post("/api/rfp/export_edits", json={"rows": rows, "filename": "out.xlsx"})

    assert _answer_fills(io.BytesIO(response.content)) == [None]


def test_export_edits_without_status_defaults_to_answered():
    response = TestClient(app).post("/api/rfp/export_edits", json={"rows": [_export_row()], "filename": "out.xlsx"})

    assert response.status_code == 200
    assert _answer_fills(io.BytesIO(response.content)) == [None]


def test_export_edits_rejects_unknown_status():
    response = TestClient(app).post("/api/rfp/export_edits", json={"rows": [_export_row(status="maybe")], "filename": "out.xlsx"})

    assert response.status_code == 422


# --- Cost rounding (output only) ---

def _cost_cells(excel_file):
    ws = openpyxl.load_workbook(excel_file).worksheets[0]
    col = [c.value for c in ws[1]].index("Cost ($)")
    return [row[col].value for row in ws.iter_rows(min_row=2)]


@pytest.mark.parametrize("dtype", [float, object])  # export_edits builds object-dtype columns
def test_writer_rounds_cost_and_keeps_callers_df(dtype):
    df = pd.DataFrame({"Question": ["q"], "Cost ($)": pd.Series([0.00123456], dtype=dtype)})

    excel = create_formatted_excel_bytes(sheets_dict={"RFP": df})

    assert _cost_cells(excel) == [0.0012]
    assert df["Cost ($)"].tolist() == [0.00123456]


def test_writer_without_cost_column():
    df = pd.DataFrame({"Question": ["q"]})

    assert openpyxl.load_workbook(create_formatted_excel_bytes(sheets_dict={"RFP": df})).sheetnames == ["RFP"]


def test_analyze_rounds_cost_at_output_only(tmp_path, monkeypatch):
    wb = openpyxl.Workbook()
    wb.active.append(["Question"])
    wb.active.append(["q"])
    path = _save(wb, tmp_path)
    questions = extract_questions_node({"rfp_input_path": path})["extracted_questions"]
    answers = [_answer_of(questions[0], cost=0.00123456)]

    body = _analyze(path, answers, monkeypatch)

    assert body["preview_data"][0]["cost"] == 0.0012
    assert _cost_cells(io.BytesIO(base64.b64decode(body["excel_base64"]))) == [0.0012]
    assert answers[0].cost == 0.00123456


def test_export_edits_rounds_cost():
    row = {"id": "[RFP] A1", "category": "Security", "question": "q", "answer": "a",
           "sources": [], "conflicts": "", "cost": 0.00123456}

    response = TestClient(app).post("/api/rfp/export_edits", json={"rows": [row], "filename": "out.xlsx"})

    assert response.status_code == 200
    assert _cost_cells(io.BytesIO(response.content)) == [0.0012]


# --- Accepted file types ---

@pytest.mark.parametrize("endpoint", ["/api/rfp/analyze", "/api/rfp/evaluate"])
@pytest.mark.parametrize("filename", ["rfp.xls", "RFP.XLS"])
def test_xls_rejected_even_without_api_key(endpoint, filename, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = TestClient(app).post(endpoint, files={"file": (filename, b"unused")})

    assert response.status_code == 400
    assert "save as .xlsx" in response.json()["detail"]


def _post_with_answers(endpoint, path, answers, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(api, "rfp_graph", SimpleNamespace(invoke=lambda *a, **k: {"final_answers": answers}))
    with open(path, "rb") as f:
        return TestClient(app).post(endpoint, files={"file": ("rfp.xlsm", f)})


def test_analyze_accepts_xlsm(tmp_path, monkeypatch):
    wb = openpyxl.Workbook()
    wb.active.append(["Question"])
    wb.active.append(["q"])
    path = _save(wb, tmp_path, "rfp.xlsm")
    _, answers = _answer_all(path)

    assert _post_with_answers("/api/rfp/analyze", path, answers, monkeypatch).status_code == 200


def test_evaluate_accepts_xlsm(tmp_path, monkeypatch):
    wb = openpyxl.Workbook()
    wb.active.append(["Question", "Expected Answer"])
    wb.active.append([None, "e"])  # blank question: no judge call
    path = _save(wb, tmp_path, "rfp.xlsm")

    assert _post_with_answers("/api/rfp/evaluate", path, [], monkeypatch).status_code == 200


def test_nodes_read_xlsm(tmp_path):
    wb = openpyxl.Workbook()
    wb.active.title = "RFP"
    wb.active.append(["ID", "Question"])
    wb.active.append(["A1", "first"])
    path = _save(wb, tmp_path, "rfp.xlsm")

    questions, answers = _answer_all(path)

    assert [q.id for q in questions] == ["[RFP] A1"]
    assert build_answer_sheets(path, answers)["RFP"]["Answer"].tolist() == ["answer to first"]


def test_run_info_round_trip_replaces_sheet_and_is_empty_for_old_files():
    from app.excel_io import RUN_INFO_SHEET, read_run_info, write_run_info
    wb = openpyxl.Workbook()
    wb.active.title = "Eval"
    assert read_run_info(wb) == {}
    write_run_info(wb, {"Agent model": "a", "Judge model": "j1"})
    write_run_info(wb, {"Agent model": "a", "Judge model": "j2", "Cost": 0.5})
    assert wb.sheetnames == ["Eval", RUN_INFO_SHEET]
    assert read_run_info(wb) == {"Agent model": "a", "Judge model": "j2", "Cost": "0.5"}
