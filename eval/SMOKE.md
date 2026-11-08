# Smoke test

Manual check after each slice. Upload `eval/fail_test.xlsx` (rebuild: `.\venv\Scripts\python eval\make_fail_test.py`) in the RFP Solver, then use "export edits".
Keep it out of `Backend/data/` (it would be ingested).

## Automated
`.\venv\Scripts\python eval\smoke.py --step <milestone just finished>` (repo root, real LLM calls, under $0.01).
Calls `/api/rfp/analyze` + `/api/rfp/export_edits` in-process (no server, no startup ingest), prints question / ID / attempts / cost / fill / dropdown / sources, then PASS/FAIL per row of "Expected per step". Exit 1 on any FAIL.
Asserts only deterministic things; attempts and which sources are cited vary per run, so they are shown, not asserted. The UI check above stays for frontend-only changes.

## Debug runner
`.\venv\Scripts\python eval\run_rfp.py <file> [--model gpt-4o-mini]` (repo root, real LLM calls): any RFP file (`.xlsx`/`.xlsm`/`.pdf`, e.g. `eval\judge_qa_test.xlsx`, `eval\pdf_rfp_test.pdf`) through `/api/rfp/analyze` in-process, like the smoke test.
Prints the agent log (judge verdicts, `[!] Invalid citations`, `[~] Citation near-miss`), then id / status / question, full answer, sources per row. No checks: read the output.

## Before/after Excel comparison
`.\venv\Scripts\python eval\compare_excel.py` (repo root) compares current output with `eval/baseline/`, captured at the commit before step 5a (`--capture` rewrites it; `--no-llm` skips the real case).
Stubbed cases (edge-case workbooks, PDF, evaluate): every cell, style and width must match. Real case (`fail_test.xlsx`): LLM text columns relaxed, structure and colours exact. Preview rows must match the baseline minus rows without an Answer; question and category are not compared (intended 5a fixes), nor is `status` (added in 5b).
Intended colour changes since the baseline are listed cell by cell in `FILL_CHANGES` in the script; do not recapture to hide a difference. The baseline holds the pre-5c `FAIL_MSG`: the script maps it to the new wording before comparing values.

## Input
| Sheet | Question | Notes |
|---|---|---|
| Security | minimum password length (ID SEC-01) | answerable from LC-POL-002 Access Control and Password Policy.pdf |
| Security | CEO's shoe size (ID SEC-02) | not answerable |
| General | removable storage media restricted? | sheet without ID column |

`Security` has a `Supported (Yes/No)` dropdown (Yes/No/Partial) placed before the `ID` column.

## Expected per step
| Check | Steps 1–3 | Step 4–5 | Step 6+ |
|---|---|---|---|
| Password | answered: not FAIL_MSG, ≥1 citation (usually LC-POL-002 Access Control and Password Policy.pdf — not asserted) | same | same |
| Password text | – | – | must contain "8 characters" (retrieval: plain similarity k=5; informational, printed as `INFO`, not asserted) |
| Shoe size | FAIL_MSG, red | same (5b: status `not_found`) | same |
| Removable media | answered: not FAIL_MSG, ≥1 citation (usually LC-POL-010 Removable Media Policy.pdf — not asserted) | same | same |
| Dropdown | value from Yes/No/Partial | same | same |
| Cost | > 0 for every question | same | same |
| Security IDs in preview | dropdown values (`Yes`/`Partial`, `No`; can duplicate): classifier fills the Yes/No column, then analyze takes it as ID column | `[Security] SEC-01`, `[Security] SEC-02` | same |
| General ID in preview | `Q-3` (row index across all sheets) | `[General] Q1` (sheet-local) | same |
| Export edits sheets | all rows in one `RFP Responses` sheet (preview IDs have no `[sheet]` prefix) | original sheets kept | same |
| Yellow rows | none | none | only for `needs_review` |
| Review note | – | – | non-empty exactly on `needs_review` rows (printed below the table) |
| No schema leak | no answer contains `sources_used`, `answer_text`, `reasoning`, `{'`, `':` | same | same |

## Baseline values (2026-11-08, demo KB, gpt-4o-mini, one run; LLM output varies)
Smoke: 12/12 PASS.
| Question | Attempts | Status | Cost ($) | Fill | Dropdown | Sources |
|---|---|---|---|---|---|---|
| Password (SEC-01) | 1, approved | answered | 0.0008 | none | Yes | LC-POL-002 Access Control and Password Policy.pdf |
| Shoe size (SEC-02) | 1 draft = FAIL_MSG, no judge | not_found | 0.0005 | red | No | – |
| Removable media (Q1) | 1, approved | answered | 0.0008 | none | – | LC-POL-010 Removable Media Policy.pdf, Velmora xlsx (near-miss logged: sheet omitted) |
