# Eval results

KB: 10 LogistiComp policy PDFs + 2 past-RFP xlsx, 241 chunks. Model: gpt-4o-mini.

## 2026-11-08 Thornvale baseline
Run: `eval/runs/2026-11-08_thornvale_baseline.xlsx`. 18/22 correct. Cost ~$0.017.

Failures:
- TF-SEC-08: wrong deduction ("90 days, not within 6 months"), dropdown No.
- TF-SEC-05: dropdown No although 7 <= 14 days.
- TF-SRV-01: judge rejected a correct answer because the question names the customer "Thornvale" → not found.
- TF-SEC-11: missed GDPR processor/controller nuance.

Noise:
- 3 false conflicts (TF-SRV-08, TF-SRV-04, TF-SEC-12).
- Citations name another customer's file.
- Most security questions categorised "Product".

## 2026-11-08 eval_set_v2 baseline
Setup: `eval/eval_set_v2.xlsx`, 52 questions (33 dev / 19 held_out). Judge gpt-6-luna (alias, effort low, measured 2026-11-08) with the clarified `generated_verdict` field (the answer's own yes/no reply, not agreement). Scores = mean (min-max) over runs; report: `eval/score_report.py`. Earlier numbers in this entry (judged with the old verdict field) are superseded.

Runs: **4o-mini** = agent gpt-4o-mini, `Evaluated_v2_run1_oldjudge` + `Evaluated_v2_run2_rules9-10`, rejudged with `eval/rejudge.py` (baseline). **fix1** = `Evaluated_v2_fix1_r1`, rejudged (1 run; see caveat). **luna** = agent gpt-6-luna, `Evaluated_v2_luna_r1` (rejudged) + `Evaluated_v2_luna_r2`.

| | 4o-mini (2 runs) | fix1 (1 run) | luna (2 runs) |
|---|---|---|---|
| Overall | 82.4 (82.0–82.8) | 83.7 | 81.3 (79.6–83.0) |
| dev | 84.6 (83.3–85.9) | 85.2 | 82.8 (80.2–85.5) |
| held_out | 78.6 (75.3–81.8) | 81.1 | 78.7 |
| Refusals | 6/6 | 6/6 | 4 (3–5)/6; answered EV-44 (2/2), EV-10, EV-22 (1/2) |
| Leak in answer text | EV-52 (2/2) | EV-52 | none |
| Leak in sources (rows) | 18.5 (18–19) | 19 | 14.5 (14–15) |

| Type (dev n / held_out n) | 4o-mini dev / held_out | fix1 dev / held_out | luna dev / held_out |
|---|---|---|---|
| answerable (6/5) | 85.0 / 67.0 | 84.2 / 70.0 | 82.5 / 62.0 |
| nuanced (5/3) | 83.0 / 70.0 | 83.0 / 65.0 | 75.0 / 72.5 |
| stale_conflict (1/1) | 95.0 / 75.0 | 100 / 75 | 95.0 / 77.5 |
| deduction (5/3) | 76.0 / 100 | 84.0 / 100 | 85.0 / 100 |
| partial (4/2) | 95.6 / 48.8 (25.0–72.5) | 92.5 / 72.5 | 93.8 / 95.0 |
| policy_conflict (1/0) | 45.0 / – | 40 / – | 100 / – |
| unanswerable (4/2) | 100 / 100 | 100 / 100 | 75.0 / 50.0 |
| leak_check (2/1) | 38.8 / 75.0 | 37.5 / 75 | 52.5 / 100 |
| past_rfp_only (5/2) | 97.5 / 100 | 97.0 / 100 | 92.5 / 100 |

Rows < 60:
- 4o-mini: EV-07 45, EV-08 20, EV-11 45, EV-13 0, EV-25 60 (20–100), EV-26 47.5 (0–95), EV-32 20, EV-37 50, EV-45 20, EV-46 45.
- fix1: EV-07 40, EV-08 20, EV-11 45, EV-13 0, EV-32 15, EV-37 50, EV-45 20, EV-46 35.
- luna: EV-08 65, EV-10 50 (0–100), EV-11 55, EV-13 15, EV-22 50 (0–100), EV-23 52.5, EV-29 52.5, EV-32 20, EV-44 0, EV-45 20, EV-46 30.

Notes:
- Capped rows with the clarified field: EV-08 (both 4o-mini runs) and EV-25 (run 2); both are real wrong conclusions ("not within 6 months", "not 10"). No false caps.
- luna agent: better on policy_conflict, partial and leaks (no customer name in answers), worse on refusals (answers unanswerable questions).
- Caveat fix1: produced by a stale backend (started before the luna judge and the verdict tag; a second backend shared port 8000), so its agent probably ran pre-fix code too. Re-run before drawing conclusions.

Noise:
- Judge: same answers (run 1) judged twice with the old field → overall differs by 0.8, max 10 per row, 34/46 judged rows identical.
- Agent: EV-26 0 vs 100, EV-25 20 vs 100 (4o-mini runs).

Judge selection:
- gpt-4o-mini-2024-07-18 misread `generated_verdict` as "agrees with expected": 8 false caps on the same 52 answers (EV-02, 12, 16, 18, 20, 32, 33, 52). gpt-6-luna with the old field still did this on EV-16 and EV-40; the clarified field fixed it.
- Reverted earlier attempt: judge-prompt rules 9–10 (Yes/No conclusion, customer names) fixed EV-08 but wrongly zeroed 7 correct answers.
