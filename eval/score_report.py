"""Markdown score report for Evaluated_*.xlsx files (output of /api/rfp/evaluate on eval/eval_set_v2.xlsx).
No LLM calls. Run: .\\venv\\Scripts\\python eval\\score_report.py <Evaluated_*.xlsx> [more runs...]
Final score per row: Expected Status not_found -> 100 if the Answer is fail text, else 0 (LLM Score ignored);
otherwise LLM Score. With several files every number is mean (min-max) across runs.
"""
import os
import re
import sys
from statistics import mean

import openpyxl
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "Backend"))
from app.agent.nodes import _CITATION_GROUP, is_fail_text
from app.excel_io import RUN_INFO_SHEET, read_run_info

# \b before the ID prefixes so words like "standards-based" don't count as "DS-".
LEAK = re.compile(r"velmora|brennholt|hamburg|leipzig|\bvsa-|\bds-", re.IGNORECASE)
SPLITS = ("dev", "held_out")
LOW = 60
REQUIRED = ["ID", "Type", "Split", "Expected Status", "Answer", "Sources", "LLM Score"]


def _text(value) -> str:
    return "" if pd.isna(value) else str(value)


def load_run(path) -> list[dict]:
    """One dict per row with an ID: id, type, split, not_found, score, leak_answer, leak_sources."""
    sheets = pd.read_excel(path, sheet_name=None)
    df = pd.concat([s for name, s in sheets.items() if name != RUN_INFO_SHEET], ignore_index=True)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")
    rows = []
    for _, r in df.iterrows():
        if not _text(r["ID"]).strip():
            continue
        answer, sources = _text(r["Answer"]), _text(r["Sources"])
        not_found = _text(r["Expected Status"]).strip() == "not_found"
        if not_found:
            score = 100.0 if is_fail_text(answer) else 0.0
        else:
            llm = pd.to_numeric(r["LLM Score"], errors="coerce")
            score = 0.0 if pd.isna(llm) else float(llm)
        rows.append({
            "id": _text(r["ID"]).strip(), "type": _text(r["Type"]).strip(), "split": _text(r["Split"]).strip(),
            "not_found": not_found, "score": score,
            # Text leak = names the agent wrote itself; cited files are counted by the Sources check.
            "refused": is_fail_text(answer),
            "leak_answer": bool(LEAK.search(_CITATION_GROUP.sub("", answer))),
            "leak_sources": bool(LEAK.search(sources)),
        })
    return rows


def _avg(rows):
    return mean(r["score"] for r in rows) if rows else None


def run_metrics(rows: list[dict]) -> dict:
    nf = [r for r in rows if r["not_found"]]
    m = {
        "overall": _avg(rows),
        "refusals": sum(r["score"] == 100 for r in nf),
        "wrong": [r["id"] for r in nf if r["score"] != 100],
        # Answerable questions answered with the fail text.
        "wrongful": [r["id"] for r in rows if not r["not_found"] and r["refused"]],
        "leak_answer": [r["id"] for r in rows if r["leak_answer"]],
        "leak_sources": [r["id"] for r in rows if r["leak_sources"]],
        "scores": {r["id"]: r["score"] for r in rows},
    }
    for split in SPLITS:
        m[split] = _avg([r for r in rows if r["split"] == split])
        for t in {r["type"] for r in rows}:
            m[(t, split)] = _avg([r for r in rows if r["type"] == t and r["split"] == split])
    return m


def fmt(values, digits=1) -> str:
    """One run: the value. Several runs: mean (min-max). Missing values -> '–'."""
    values = [v for v in values if v is not None]
    if not values:
        return "–"
    if len(values) == 1:
        return f"{values[0]:.{digits}f}"
    return f"{mean(values):.1f} ({min(values):.{digits}f}–{max(values):.{digits}f})"


def fmt_ids(id_lists, order) -> str:
    """IDs found in any run, in sheet order; with several runs each gets (runs with it/runs)."""
    n = len(id_lists)
    hits = {i: sum(i in ids for ids in id_lists) for i in order}
    shown = [i if n == 1 else f"{i} ({k}/{n})" for i, k in hits.items() if k]
    return ", ".join(shown) or "–"


def run_info_line(path) -> str:
    info = read_run_info(openpyxl.load_workbook(path, read_only=True))
    if not info:
        return "no run info"
    return "; ".join(f"{k}: {v}" for k, v in info.items())


def report(paths) -> str:
    runs = [load_run(p) for p in paths]
    metrics = [run_metrics(rows) for rows in runs]
    first = runs[0]
    order = [r["id"] for r in first]
    info = {r["id"]: r for r in first}
    types = list(dict.fromkeys(r["type"] for r in first))
    nf_total = sum(r["not_found"] for r in first)

    def col(key):
        return [m[key] for m in metrics]

    out = [f"# Score report ({len(paths)} run{'s' if len(paths) > 1 else ''})", ""]
    out += [f"- {os.path.basename(str(p))} ({run_info_line(p)})" for p in paths] + [""]

    out += ["## Mean score", "| Set | Rows | Mean |", "|---|---|---|",
            f"| Overall | {len(first)} | {fmt(col('overall'))} |"]
    for split in SPLITS:
        out.append(f"| {split} | {sum(r['split'] == split for r in first)} | {fmt(col(split))} |")
    out.append("")

    out += ["## By type", "| Type | dev n | dev mean | held_out n | held_out mean |", "|---|---|---|---|---|"]
    for t in types:
        cells = []
        for split in SPLITS:
            cells += [str(sum(r["type"] == t and r["split"] == split for r in first)), fmt(col((t, split)))]
        out.append(f"| {t} | " + " | ".join(cells) + " |")
    out.append("")

    wrong = col("wrong")
    out += ["## Not found",
            f"- Correct refusals: {fmt(col('refusals'), 0)}/{nf_total}",
            f"- Wrong answers (answered an unanswerable question): {fmt([len(w) for w in wrong], 0)}: {fmt_ids(wrong, order)}"]
    wrongful = col("wrongful")
    by_split = ", ".join(f"{s} {fmt([sum(info[i]['split'] == s for i in w) for w in wrongful], 0)}" for s in SPLITS)
    out += [(f"- Wrongful refusals (answerable question answered with the fail text): "
             f"{fmt([len(w) for w in wrongful], 0)} ({by_split}): {fmt_ids(wrongful, order)}"), ""]

    out += ["## Leaks", "| Where | Rows | IDs |", "|---|---|---|"]
    for key, label in (("leak_answer", "Answer"), ("leak_sources", "Sources")):
        lists = col(key)
        out.append(f"| {label} | {fmt([len(ids) for ids in lists], 0)} | {fmt_ids(lists, order)} |")
    out.append("")

    out += [f"## Rows scoring < {LOW}", "| ID | Type | Split | Score |", "|---|---|---|---|"]
    low = [i for i in order if any(m["scores"].get(i, 100) < LOW for m in metrics)]
    for i in low:
        score = fmt([m["scores"].get(i) for m in metrics], 0)
        out.append(f"| {i} | {info[i]['type']} | {info[i]['split']} | {score} |")
    if not low:
        out.append("| – | | | |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python eval/score_report.py <Evaluated_*.xlsx> [more runs...]")
    sys.stdout.reconfigure(encoding="utf-8")
    print(report(sys.argv[1:]))
