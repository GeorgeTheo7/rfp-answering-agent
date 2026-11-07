"""Smoke test: runs eval/fail_test.xlsx through /api/rfp/analyze and /api/rfp/export_edits,
prints a per-question table and PASS/FAIL for the checks in eval/SMOKE.md for the given step.
Real LLM calls (costs a few tenths of a cent). No app startup -> no startup ingest.
Run: .\\venv\\Scripts\\python eval\\smoke.py --step <milestone>
"""
import argparse
import base64
import builtins
import io
import os
import re
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "Backend"))
sys.stdout.reconfigure(encoding="utf-8")
# Smoke runs shouldn't send LangSmith traces (load_dotenv doesn't override these).
for var in ("LANGSMITH_TRACING", "LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING", "LANGCHAIN_TRACING_V2"):
    os.environ[var] = "false"

from fastapi.testclient import TestClient
from langchain_core.vectorstores import VectorStoreRetriever
from openpyxl import load_workbook

from app.config import FAIL_MSG
from app.main import app

RED = "00FFC7CE"
YELLOW = "00FFEB9C"
DROPDOWN_COL = "Supported (Yes/No)"
DROPDOWN_VALUES = {"Yes", "No", "Partial"}

parser = argparse.ArgumentParser()
parser.add_argument("--step", type=int, required=True, help="milestone just finished (1-7)")
parser.add_argument("--model", default="gpt-4o-mini")
args = parser.parse_args()
step = args.step

# --- Attempt counting: each question runs in a worker thread. Remember which question a
# thread last retrieved for, and attribute that thread's judge log lines to it.
current_q = {}
attempts = {}  # question text -> "N (approved | gave up)"
_retriever_invoke = VectorStoreRetriever.invoke
def tracking_invoke(self, input, *a, **k):
    current_q[threading.get_ident()] = input
    return _retriever_invoke(self, input, *a, **k)
VectorStoreRetriever.invoke = tracking_invoke

_print = builtins.print
def tracking_print(*a, **k):
    m = re.search(r"Attempt (\d+): (Answer Approved|Max revisions)", " ".join(str(x) for x in a))
    q = current_q.get(threading.get_ident())
    if m and q:
        attempts[q] = f"{m.group(1)} ({'approved' if 'Approved' in m.group(2) else 'gave up'})"
    _print(*a, **k)
builtins.print = tracking_print

# --- Run
client = TestClient(app)  # no `with` -> lifespan (startup ingest) not run
with open(os.path.join(ROOT, "eval", "fail_test.xlsx"), "rb") as f:
    r = client.post("/api/rfp/analyze", files={"file": ("fail_test.xlsx", f)}, data={"model": args.model})
r.raise_for_status()
body = r.json()
rows = body["preview_data"]

fills = {}  # question text -> Answer cell fill (None = no fill)
wb = load_workbook(io.BytesIO(base64.b64decode(body["excel_base64"])))
for ws in wb.worksheets:
    hdr = [c.value for c in ws[1]]
    if "Question" not in hdr or "Answer" not in hdr:
        continue
    qi, ai = hdr.index("Question"), hdr.index("Answer")
    for xrow in ws.iter_rows(min_row=2):
        cell = xrow[ai]
        fills[str(xrow[qi].value)] = cell.fill.fgColor.rgb if cell.fill and cell.fill.fill_type else None

export = client.post("/api/rfp/export_edits", json={"rows": rows, "filename": "smoke.xlsx"})
export.raise_for_status()
export_sheets = load_workbook(io.BytesIO(export.content)).sheetnames

# --- Table
def attempts_of(row):
    if row["question"] in attempts:
        return attempts[row["question"]]
    return "1 (draft FAIL_MSG)" if row["answer"].strip() == FAIL_MSG else "?"

def fill_name(fill):
    return {None: "none", RED: "red", YELLOW: "yellow"}.get(fill, fill)

_print("\n=== RESULTS ===")
table = [("Question", "ID", "Attempts", "Status", "Cost ($)", "Fill", "Dropdown", "Sources")]
for row in rows:
    table.append((row["question"][:45], row["id"], attempts_of(row), row.get("status", ""), f"{row['cost']:.4f}",
                  fill_name(fills.get(row["question"])), row["status_values"].get(DROPDOWN_COL, ""),
                  ", ".join(row["sources"])))
widths = [max(len(str(t[i])) for t in table) for i in range(len(table[0]))]
for t in table:
    _print(" | ".join(str(v).ljust(w) for v, w in zip(t, widths)))
_print(f"Export edits sheets: {export_sheets}")
for row in rows:
    if row.get("review_note"):
        _print(f"Review note {row['id']}: {row['review_note']}")

# --- Checks (eval/SMOKE.md, "Expected per step")
def find(word):
    return next(row for row in rows if word in row["question"].lower())
pw, shoe, media = find("password"), find("shoe"), find("removable")
_print(f'INFO password contains "8 characters" (not asserted): {"yes" if "8 characters" in pw["answer"] else "no"}')

# Only deterministic properties are asserted; attempts and which sources are cited vary per run
# (shown in the table above, not checked).
def answered(row):
    a = row["answer"]
    return a.strip() != FAIL_MSG and "SYSTEM ERROR" not in a and len(row["sources"]) >= 1

# Field names / dict syntax in the text = structured-output fields leaked into answer_text.
SCHEMA_LEAKS = ["sources_used", "answer_text", "reasoning", "{'", "':"]

checks = [
    ("Password answered (not FAIL_MSG, >=1 citation)", answered(pw)),
    ("Shoe size = FAIL_MSG, red", shoe["answer"].strip() == FAIL_MSG and fills.get(shoe["question"]) == RED),
    ("Removable media answered (not FAIL_MSG, >=1 citation)", answered(media)),
    ("Dropdown values from Yes/No/Partial",
     all(row["status_values"].get(DROPDOWN_COL) in DROPDOWN_VALUES for row in (pw, shoe))),
    ("Cost > 0 for every question", all(row["cost"] > 0 for row in rows)),
    ("No schema leak in answers", not any(s in row["answer"] for row in rows for s in SCHEMA_LEAKS)),
]
if "status" in shoe:  # from step 5b
    checks.append(("Shoe size status = not_found", shoe["status"] == "not_found"))
if step <= 3:
    checks += [
        ("Security IDs = dropdown values (known ID bug)", {pw["id"], shoe["id"]} <= DROPDOWN_VALUES),
        ("General ID = Q-3", media["id"] == "Q-3"),
        ("Export edits: one 'RFP Responses' sheet", export_sheets == ["RFP Responses"]),
    ]
else:
    checks += [
        ("Security IDs = [Security] SEC-01, SEC-02", {pw["id"], shoe["id"]} == {"[Security] SEC-01", "[Security] SEC-02"}),
        ("General ID sheet-local = [General] Q1", media["id"] == "[General] Q1"),
        ("Export edits: original sheets kept", export_sheets == ["Security", "General"]),
    ]
other_fills = [row for row in rows if fills.get(row["question"]) not in (None, RED)]
if step < 6:
    checks.append(("No yellow rows", not other_fills))
else:
    checks.append(("Yellow only for needs_review", all(row.get("status") == "needs_review" for row in other_fills)))
    checks.append(("Review note iff needs_review",
                   all(bool(row.get("review_note")) == (row.get("status") == "needs_review") for row in rows)))

_print(f"\n=== CHECKS (step {step}) ===")
for name, ok in checks:
    _print(f"{'PASS' if ok else 'FAIL'}  {name}")
failed = sum(not ok for _, ok in checks)
_print(f"\n{len(checks) - failed}/{len(checks)} passed")
sys.exit(1 if failed else 0)
