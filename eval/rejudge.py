"""Re-judge an Evaluated_*.xlsx with another judge model, without re-running the agent.
Real LLM calls (judge only). Run: .\\venv\\Scripts\\python eval\\rejudge.py <Evaluated_*.xlsx> <judge model>
<judge model> must be a key of MODEL_SETTINGS in Backend/app/config.py. For every row with a question and an
expected answer (as in /api/rfp/evaluate), run_llm_judge compares the existing Answer with the Expected Answer;
LLM Score / LLM Reasoning are overwritten, everything else (columns, Cost ($), colours) is kept.
Run info sheet: judge fields replaced, "Rejudged at" / "Rejudge commit" added; agent fields kept
("unknown" for older files without the sheet).
Writes <input>_rejudged_<model>.xlsx next to the input and prints the total judge cost.
Free-text judging only (no categorical / dropdown scoring).
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "Backend"))
from app import evaluation
from app.config import MODEL_SETTINGS
from app.evaluation import judge_info, now_iso, run_llm_judge
from app.excel_io import RUN_INFO_SHEET, read_run_info, write_run_info

REQUIRED = ["Question", "Expected Answer", "Answer", "LLM Score", "LLM Reasoning"]


def _text(value) -> str:
    return "" if value is None else str(value)


def output_path(input_path: str, model: str) -> str:
    base, ext = os.path.splitext(input_path)
    return f"{base}_rejudged_{model}{ext}"


def rejudge(input_path: str, model: str, workers: int = 5) -> tuple[str, float, int]:
    """(output path, total judge cost, rows judged)."""
    if model not in MODEL_SETTINGS:
        raise ValueError(f"Unknown judge model {model!r}; choose one of {list(MODEL_SETTINGS)}")
    wb = openpyxl.load_workbook(input_path)
    jobs = []  # (sheet, row number, header->column index, question, answer, expected)
    for ws in wb.worksheets:
        if ws.title == RUN_INFO_SHEET:
            continue
        header = {_text(c.value).strip(): c.column for c in ws[1] if _text(c.value).strip()}
        missing = [c for c in REQUIRED if c not in header]
        if missing:
            raise ValueError(f"{input_path} [{ws.title}]: missing columns {missing}")
        for row in range(2, ws.max_row + 1):
            question = _text(ws.cell(row, header["Question"]).value)
            expected = _text(ws.cell(row, header["Expected Answer"]).value)
            if question.strip() and expected.strip():
                jobs.append((ws, row, header, question, _text(ws.cell(row, header["Answer"]).value), expected))

    def judge(job):
        _, _, _, question, answer, expected = job
        return run_llm_judge(question, answer, expected, judge_model=model)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(judge, jobs))

    total = 0.0
    for (ws, row, header, *_), (result, cost) in zip(jobs, results):
        ws.cell(row, header["LLM Score"]).value = result.score
        ws.cell(row, header["LLM Reasoning"]).value = result.reasoning
        total += cost
    info = read_run_info(wb) or {"Agent model": "unknown", "Timestamp": "unknown", "Git commit": "unknown"}
    info.update(judge_info(model))
    info.update({"Rejudged at": now_iso(), "Rejudge commit": evaluation.CODE_COMMIT})
    write_run_info(wb, info)
    out = output_path(input_path, model)
    wb.save(out)
    return out, total, len(jobs)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python eval/rejudge.py <Evaluated_*.xlsx> <judge model>")
    sys.stdout.reconfigure(encoding="utf-8")
    for var in ("LANGSMITH_TRACING", "LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING", "LANGCHAIN_TRACING_V2"):
        os.environ[var] = "false"
    out, total, n = rejudge(sys.argv[1], sys.argv[2])
    print(f"Judged {n} rows with {sys.argv[2]} -> {out}")
    print(f"Total judge cost: ${total:.4f}")
