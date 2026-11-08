"""Compares what the API exports now against eval/baseline/ (captured before a refactor).
Stubbed cases (no LLM, edge-case workbooks, PDF, evaluate): every cell must match exactly.
Real case (eval/fail_test.xlsx, under $0.01): structure and colours; LLM text columns relaxed.
Run from the repo root:
  .\\venv\\Scripts\\python eval\\compare_excel.py --capture    write the baseline
  .\\venv\\Scripts\\python eval\\compare_excel.py [--no-llm]   compare, exit 1 on any difference
"""
import argparse
import base64
import io
import json
import os
import sys
import tempfile
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "Backend"))
sys.stdout.reconfigure(encoding="utf-8")
for var in ("LANGSMITH_TRACING", "LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING", "LANGCHAIN_TRACING_V2"):
    os.environ[var] = "false"

import openpyxl
from fastapi.testclient import TestClient
from openpyxl.worksheet.datavalidation import DataValidation

import app.agent.graph as graph_module
import app.agent.nodes as nodes
from app import api
from app.agent.schemas import Answer, Question, RFPQuestions, SourceRef
from app.config import FAIL_MSG, FAIL_MSG_PREFIX, OLD_FAIL_MSG_PREFIX
from app.evaluation import EvaluationResult
from app.excel_io import detect_status_columns
from app.main import app as fastapi_app

BASELINE = os.path.join(ROOT, "eval", "baseline")
FAIL_TEST = os.path.join(ROOT, "eval", "fail_test.xlsx")
client = TestClient(fastapi_app)  # no `with` -> lifespan (startup ingest) not run

# Intended changes since the baseline: {case: {cell: (fill before, fill after)}}. Each must happen exactly.
# Step 5b: the exact Answer column is coloured, not the first header containing "answer".
FILL_CHANGES = {"stub_eval_text": {"One!C4": ("00FFC7CE", None), "One!D4": (None, "00FFC7CE")}}

# Intended wording change, step 5c: the baseline holds the old FAIL_MSG.
OLD_FAIL_MSG = FAIL_MSG.replace(FAIL_MSG_PREFIX, OLD_FAIL_MSG_PREFIX)

def _reword(value):
    return value.replace(OLD_FAIL_MSG, FAIL_MSG) if isinstance(value, str) else value

# --- Input workbooks ---
def _dropdown(ws, cells, values='"Yes,No,Partial"'):
    dv = DataValidation(type="list", formula1=values)
    ws.add_data_validation(dv)
    dv.add(cells)

def edge_workbook(path):
    wb = openpyxl.Workbook()
    main = wb.active
    main.title = "Main"  # int IDs, blank-question row, dropdown, category column
    main.append(["ID", "Question", "Category", "Supported (Yes/No)"])
    main.append([1, "Do you encrypt data?", "Security", None])
    main.append([2, None, None, None])
    main.append([3, "What is the CEO's shoe size?", "Product", None])
    main.append([None, "Is there a conflict in the API docs?", None, None])
    _dropdown(main, "D2:D5")
    dups = wb.create_sheet("Dups")  # duplicate IDs, existing Answer and Cost columns
    dups.append(["ID", "Question", "Answer", "Cost ($)"])
    dups.append(["A1", "first duplicate", "old answer", 5.0])
    dups.append(["A1", "second duplicate", None, None])
    dups.append(["A3", None, "kept, no question", 1.0])  # blank cost here = 500 before step 5a
    reqs = wb.create_sheet("Reqs")  # different question header, no ID column
    reqs.append(["Requirement", "Notes"])
    reqs.append(["Encrypt data at rest", "note"])
    reqs.append([None, "only a note"])
    reqs.append(["Rotate the keys", None])
    wb.create_sheet("IdOnly").append(["ID"])  # no question column: not asked, still exported
    wb["IdOnly"].append(["X1"])
    wb.create_sheet("Empty")
    wb.create_sheet("HeaderOnly").append(["Question"])
    wb.save(path)

def eval_text_workbook(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "One"
    ws.append(["ID", "Question", "Expected Answer"])
    ws.append([1, "Do you encrypt data?", "Yes, AES-256"])
    ws.append([2, None, "no question"])
    ws.append([3, "What is the CEO's shoe size?", OLD_FAIL_MSG])  # old files keep the old wording: still excluded
    ws.append([4, "No expectation here", None])
    two = wb.create_sheet("Two")  # no ID, different question header: skipped by the evaluator today
    two.append(["Requirement", "Expected Answer"])
    two.append(["Rotate the keys", "Yearly"])
    three = wb.create_sheet("Three")  # no ID value -> fallback ID
    three.append(["Question", "Expected Answer"])
    three.append(["Do you have MFA?", "Yes"])
    wb.save(path)

def eval_dropdown_workbook(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "One"
    ws.append(["ID", "Question", "Compliance"])
    ws.append(["C1", "Do you encrypt data?", "Yes"])  # stub picks the first value: match
    ws.append(["C2", "Do you have MFA?", "No"])       # mismatch
    ws.append(["C3", None, "Partial"])
    ws.append(["C4", "No expectation here", None])
    _dropdown(ws, "C2:C5")
    two = wb.create_sheet("Two")
    two.append(["Question", "Other"])
    two.append(["Rotate the keys?", "x"])
    wb.save(path)

# --- LLM stubs: the real endpoints, nodes and writers run; only LLM calls are replaced ---
class StubQuestionGraph:
    def invoke(self, state):
        q = state["question"]
        text = FAIL_MSG if "shoe" in q.text.lower() else f"Answer to {q.text} [**Source: policy.pdf (Page 1)**]"
        draft = Answer(question_id="", question_text="", assigned_analyst="", answer_text=text, sources_used=[])
        return nodes.finalize_node({
            **state,
            "draft": draft,
            "allowed_sources": [SourceRef("policy.pdf", "", "Page 1")],
            "conflicts": "**Conflict:** a vs b" if "conflict" in q.text.lower() else "",
            "status_map": {s.column: s.allowed_values[0] for s in q.status_specs},
        })

class StubLoader:
    def __init__(self, path):
        pass
    def load(self):
        return [type("Doc", (), {"page_content": "stub rfp"})()]

class StubLLM:
    """Stands in for ChatOpenAI in the PDF path of the extract node."""
    def __init__(self, **kwargs):
        pass
    def with_structured_output(self, schema):
        return self
    def invoke(self, prompt):
        return RFPQuestions(questions=[
            Question(id="Q2", text="Do you encrypt data?", category="Security"),
            Question(id="Q10", text="What is the CEO's shoe size?", category="Product"),
            Question(id="Q1", text="Do you have an API?", category="Tech"),
        ])

def _stub_judge(question, generated, expected, model_name="stub"):
    return EvaluationResult(score=len(expected) % 101, reasoning=f"judged {question}"), 0.001

def stubbed(fn):
    with (patch.object(graph_module, "question_graph", StubQuestionGraph()),
          patch.object(graph_module, "calculate_cost", lambda model, cb: 0.00123456),
          patch.object(nodes, "PyMuPDFLoader", StubLoader),
          patch.object(nodes, "ChatOpenAI", StubLLM),
          patch.object(api, "run_llm_judge", _stub_judge),
          patch.dict(os.environ, {"OPENAI_API_KEY": "stub"})):
        return fn()

# --- Running a case: returns the exported Excel bytes + the JSON part of the response ---
def _post(endpoint, path, filename):
    with open(path, "rb") as f:
        r = client.post(endpoint, files={"file": (filename, f)}, data={"model": "gpt-4o-mini"})
    if r.status_code != 200:
        raise RuntimeError(f"{endpoint} {filename}: {r.status_code} {r.text[:500]}")
    body = r.json()
    return base64.b64decode(body.pop("excel_base64")), body

def run_cases(out_dir, tmp_dir, llm):
    def workbook(build, name):
        path = os.path.join(tmp_dir, name)
        build(path)
        return path
    pdf = os.path.join(tmp_dir, "rfp.pdf")
    open(pdf, "wb").close()
    cases = {
        "stub_edge": lambda: stubbed(lambda: _post("/api/rfp/analyze", workbook(edge_workbook, "edge.xlsx"), "edge.xlsx")),
        "stub_pdf": lambda: stubbed(lambda: _post("/api/rfp/analyze", pdf, "rfp.pdf")),
        "stub_eval_text": lambda: stubbed(lambda: _post("/api/rfp/evaluate", workbook(eval_text_workbook, "e1.xlsx"), "e1.xlsx")),
        "stub_eval_dropdown": lambda: stubbed(lambda: _post("/api/rfp/evaluate", workbook(eval_dropdown_workbook, "e2.xlsx"), "e2.xlsx")),
    }
    if llm:
        cases["real_fail_test"] = lambda: _post("/api/rfp/analyze", FAIL_TEST, "fail_test.xlsx")
    os.makedirs(out_dir, exist_ok=True)
    for name, run in cases.items():
        excel, body = run()
        with open(os.path.join(out_dir, f"{name}.xlsx"), "wb") as f:
            f.write(excel)
        with open(os.path.join(out_dir, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=1)
    return list(cases)

# --- Comparing ---
def _cell_style(cell):
    fill = cell.fill.fgColor.rgb if cell.fill and cell.fill.fill_type else None
    return fill, bool(cell.font.b), cell.font.sz, cell.alignment.wrap_text, cell.alignment.vertical, cell.alignment.horizontal

def _relaxed_equal(col, a, b, allowed):
    """Real-LLM case: which differences in the LLM-written columns are acceptable."""
    if col == "Conflicts":
        return True
    if col in ("Answer", "Sources"):
        return bool(a) == bool(b)
    if col == "Cost ($)":
        return (a or 0) > 0 and (b or 0) > 0
    if col in allowed:
        return (a in allowed[col] and b in allowed[col]) or a == b
    return a == b

def compare_excel(before_path, after_path, allowed=None, fill_changes=None):
    """allowed=None: exact. Otherwise {dropdown column: values} and LLM columns are relaxed.
    fill_changes: {cell: (fill before, fill after)}, see FILL_CHANGES."""
    fill_changes = fill_changes or {}
    problems = []
    before, after = openpyxl.load_workbook(before_path), openpyxl.load_workbook(after_path)
    # Run info (models, time, commit) was added to evaluated files after the baseline and varies per run.
    after_sheets = [s for s in after.sheetnames if s != "Run info"]
    if before.sheetnames != after_sheets:
        return [f"sheets {before.sheetnames} != {after_sheets}"]
    for ws_b in before.worksheets:
        ws_a = after[ws_b.title]
        if (ws_b.max_row, ws_b.max_column) != (ws_a.max_row, ws_a.max_column):
            problems.append(f"{ws_b.title}: size {ws_b.dimensions} != {ws_a.dimensions}")
            continue
        headers = [c.value for c in ws_b[1]]
        widths_b = {k: v.width for k, v in ws_b.column_dimensions.items()}
        widths_a = {k: v.width for k, v in ws_a.column_dimensions.items()}
        if widths_b != widths_a:
            problems.append(f"{ws_b.title}: widths {widths_b} != {widths_a}")
        for row_b, row_a in zip(ws_b.iter_rows(), ws_a.iter_rows()):
            for cell_b, cell_a in zip(row_b, row_a):
                where = f"{ws_b.title}!{cell_b.coordinate}"
                style_b, style_a = _cell_style(cell_b), _cell_style(cell_a)
                if where in fill_changes:
                    if (style_b[0], style_a[0]) != fill_changes[where]:
                        problems.append(f"{where}: fill {style_b[0]} -> {style_a[0]}, expected {fill_changes[where]}")
                    style_b, style_a = style_b[1:], style_a[1:]
                if style_b != style_a:
                    problems.append(f"{where}: style {style_b} != {style_a}")
                col = headers[cell_b.column - 1]
                same = _reword(cell_b.value) == _reword(cell_a.value)
                if allowed is not None and cell_b.row > 1:
                    same = _relaxed_equal(col, cell_b.value, cell_a.value, allowed)
                if not same or type(cell_b.value) is not type(cell_a.value) and allowed is None:
                    problems.append(f"{where} [{col}]: {cell_b.value!r} != {cell_a.value!r}")
    return problems

def compare_preview(before, after, exact):
    """Intended 5a change: rows without an Answer leave the preview; question and category
    are corrected. Everything else about the surviving rows must be the same, in the same order."""
    problems = []
    after_ids = [r["id"] for r in after]
    kept = [r for r in before if r["id"] in after_ids]
    if [r["id"] for r in kept] != after_ids:
        problems.append(f"preview ids {[r['id'] for r in kept]} != {after_ids}")
    for r in before:
        if r["id"] not in after_ids and r["question"].strip() and r["answer"].strip():
            problems.append(f"preview lost an answered row: {r['id']}")
    if exact:
        for b, a in zip(kept, after):
            for key in ("answer", "sources", "conflicts", "cost", "status_values"):
                if b[key] != a[key]:
                    problems.append(f"preview {b['id']} {key}: {b[key]!r} != {a[key]!r}")
    return problems

def compare_case(name, after_dir):
    def load(folder):
        with open(os.path.join(folder, f"{name}.json"), encoding="utf-8") as f:
            return json.loads(_reword(f.read()))
    real = name.startswith("real_")
    allowed = None
    if real:
        allowed = {s["column"]: s["allowed_values"] for specs in detect_status_columns(FAIL_TEST).values() for s in specs}
    problems = compare_excel(os.path.join(BASELINE, f"{name}.xlsx"), os.path.join(after_dir, f"{name}.xlsx"), allowed,
                             FILL_CHANGES.get(name))
    before, after = load(BASELINE), load(after_dir)
    if before.get("filename") != after.get("filename"):
        problems.append(f"filename {before.get('filename')} != {after.get('filename')}")
    if "preview_data" in before:
        problems += compare_preview(before["preview_data"], after["preview_data"], exact=not real)
    else:  # evaluate: the whole response must match
        if before != after:
            problems.append(f"evaluate response differs:\n  {before}\n  {after}")
    return problems

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true", help=f"write the baseline to {BASELINE}")
    parser.add_argument("--no-llm", action="store_true", help="skip the real fail_test case")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        if args.capture:
            names = run_cases(BASELINE, tmp, llm=not args.no_llm)
            print(f"\nBaseline written to {BASELINE}: {names}")
            sys.exit(0)
        out = os.path.join(tmp, "after")
        names = run_cases(out, tmp, llm=not args.no_llm)
        print("\n=== COMPARE AGAINST BASELINE ===")
        failed = 0
        for name in names:
            problems = compare_case(name, out)
            print(f"{'FAIL' if problems else 'PASS'}  {name}")
            for p in problems:
                print(f"      {p}")
            failed += bool(problems)
    print(f"\n{len(names) - failed}/{len(names)} cases match")
    sys.exit(1 if failed else 0)
