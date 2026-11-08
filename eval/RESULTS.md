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
