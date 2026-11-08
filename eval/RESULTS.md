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
Setup: `eval/eval_set_v2.xlsx`, 52 questions (33 dev / 19 held_out). Agent gpt-4o-mini, judge gpt-6-luna (alias, effort low, measured 2026-11-08). Scores = mean (min-max) over 2 agent runs (`Evaluated_v2_run1_oldjudge`, `Evaluated_v2_run2_rules9-10`, both rejudged with `eval/rejudge.py`; report: `eval/score_report.py`).

Overall 83.1 (82.2–84.0); dev 85.4 (85.3–85.5); held_out 79.2 (76.8–81.6).

| Type | dev n | dev | held_out n | held_out |
|---|---|---|---|---|
| answerable | 6 | 84.2 | 5 | 67.5 (67–68) |
| nuanced | 5 | 84.0 | 3 | 71.7 (70.0–73.3) |
| stale_conflict | 1 | 100 | 1 | 75 |
| deduction | 5 | 84.0 | 3 | 100 |
| partial | 4 | 91.9 (91.2–92.5) | 2 | 51.2 (25.0–77.5) |
| policy_conflict | 1 | 40.0 (35–45) | 0 | – |
| unanswerable | 4 | 100 | 2 | 100 |
| leak_check | 2 | 40 | 1 | 75 |
| past_rfp_only | 5 | 97.0 | 2 | 100 |

- Refusals: 6/6 correct, no unanswerable question answered.
- Leaks: answer text EV-52 (both runs, "Velmora's administrators"); citations of other customers' files in 18–19 rows.
- Rows < 60: EV-07 40 (35–45), EV-08 20, EV-11 45, EV-13 0, EV-26 50 (0–100), EV-32 15, EV-37 52.5 (50–55), EV-45 20, EV-46 50 (45–55).

Noise:
- Judge: same answers (run 1) judged twice → overall differs by 0.8, max 10 per row, 34/46 judged rows identical.
- Agent: EV-26 scored 0 in one run and 100 in the other.

Judge selection:
- gpt-4o-mini-2024-07-18 misread `generated_verdict` as "agrees with expected": 8 false caps on the same 52 answers (EV-02, 12, 16, 18, 20, 32, 33, 52). gpt-6-luna capped only EV-08, correctly.
- Reverted earlier attempt: judge-prompt rules 9–10 (Yes/No conclusion, customer names) fixed EV-08 but wrongly zeroed 7 correct answers.
