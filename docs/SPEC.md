# Backend Cleanup Spec (v2.0)

## Goal
Portfolio project for agentic-AI roles. Optimize for a ~10-min reviewer skim: readable structure, visible graph, tests. Behaviour preserved unless a decision below changes it.

## Scope
**In:** bug fixes, restructure into new layout, agent-quality items (judge sees question, reasoning-first, citation validation, `needs_review`, judge loop as subgraph), `status` enum, English cleanup.
**Out:** see Later.

## Decisions
1. **Inputs:** RFP + knowledge = PDF and `.xlsx`/`.xlsm`. `.xls` → 400 "save as .xlsx". *Honest error > silent degraded path.*
2. **Ingestion dedup:** identity = filename, freshness = `content_hash` (SHA-256 of file bytes) in chunk metadata, with `chunk_count`; chunk IDs `{filename}:{content_hash}:{i}`. Startup and upload share one decision: new name → ingest; same hash, complete → skip; same hash, found ≠ `chunk_count` → delete that hash's chunks, re-ingest; new hash → ingest, delete old-hash chunks only after success; no hash (legacy) → skip + log. Old hashes left by a crash are deleted even on skip. *Policies are revised under the same name; a failed replace must not lose the old version.*
3. **Ingestion:** one shared `ingest()`; log failures (no silent `continue`); Excel ingests without LlamaParse key; writes to the single store. *Currently duplicated, silent.*
4. **Retrieval:** one-time re-ingest in step 3; collection renamed from the prototype name to `knowledge_base` (config). Chunking 1500/150, `text-embedding-3-small` unchanged. *Pay re-ingest once; keep retrieval fixed.* Done (original private knowledge base): 296 → 282 chunks, ~330 LlamaParse credits; old collection kept for v1 comparison. Retrieval diagnostics must use the full question text.
   **Changed (step 6):** draft retriever now MMR k=5, fetch_k=20, λ=0.7 (config; was default λ=0.5); conflict audit unchanged. Evidence (embedding diagnostic, 2 questions): answer chunks at similarity ranks 3–4 (password question, one other eval question) were dropped by MMR λ=0.5 in favour of past-RFP rows; Excel = 463/745 chunks on the original private knowledge base. Simulated λ=0.7 returns both. Not yet measured by eval; noise ≈ ±5 points, needs ≥2 runs per setting on eval set v2. Fallbacks: similarity slots 3 PDF + 2 Excel; reranker.
   **Changed again (2026-11-08):** draft retriever now plain similarity k=5 (`RETRIEVAL_SEARCH_TYPE`, default "similarity"; MMR still selectable). Evidence: `eval/retrieval_eval.py` on the demo KB (no LLM): fact recall 43/46 vs 40/46 for MMR λ=0.7, past-RFP chunks 1.9 per question in both; MMR dropped the fact chunks of EV-11, EV-32, EV-45 (similarity ranks 4–5). Quota 4 PDF + 2 Excel and MMR λ=0.9 were not better (43/46, 41/46). Answer scores not yet re-measured. *Fewer lost facts at no extra past-RFP rows.*
5. **Agent approach:** restructure in place, not rewrite. Split with same behaviour first, then one logic change per commit. *Changes stay attributable.*
6. **Errors:** one try/except wrapper around each question's subgraph → `status=error`. *Same as today, one place.*
7. **Conflict audit** keeps its own similarity search (k=6). *No behaviour change.*
8. **Status:** `status: answered | not_found | needs_review | error`, set by code in the graph; sent to frontend; Excel colours red = not_found/error, yellow = needs_review. `FAIL_MSG` = display text, and until step 6 also the LLM's only "found nothing" signal (`is_fail_text` for status; exact match for routing and clearing sources). The evaluator still reads it in expected answers from files, which have no status. Old files keep the pre-5c wording (`OLD_FAIL_MSG_PREFIX`), so `is_fail_text` recognises both; only the new wording is written. A human edit in the UI sets `answered`. *Replaces string-matching contracts.*
9. **Eval deferred.** Expected answers in the eval set are unreviewed old agent output (several rows known wrong), so scores would measure agreement with v1, not accuracy. v1 preserved for later comparison: git tag `v1-before-cleanup` + backup of `Backend/chroma_db/` outside the repo (gitignored, LlamaParse not reproducible → backup before step 3). Eval set moved to `eval/eval_set_v1.xlsx`.
10. **Limits:** none. Concurrency 5, `max_revisions = 2` (up to 3 drafts / 3 judge calls, as today), both in config. Cost rounded to 4 decimals.
11. **Layout:** 11 files (below). Split a file only past ~300 lines. *One job per file without thinning 1,400 lines.*
12. **API:** response shape unchanged (`preview_data`, `excel_base64`, `filename`) + `status`. Preview rows built from `Answer` objects (fixes category-by-row-index shift). Rows without a question have no `Answer`, so they leave the preview and `export_edits`; they stay in the exported Excel. Frontend: use `status`, fix grammar only.
13. **Tests:** pytest, no LLM calls or network. Pure functions: column detection, dropdown parsing, `_canonical_value`, citation validation, ingest decision, export ID parsing. Ingest + upload dedup: real Chroma in `tmp_path`, fake embeddings (never the real store).

## Layout
```
Backend/app/
  main.py        app, lifespan (startup ingest), CORS
  config.py      paths, models, k, chunking, rounds, concurrency, pricing, FAIL_MSG, collection
  api.py         endpoints + request/response models
  store.py       lazy Chroma singleton (no import side effects)
  ingestion.py   loaders + ingest()
  excel_io.py    read (question/ID/category cols, dropdowns) + write/export
  agent/
    prompts.py   all prompts
    schemas.py   LLM-facing + internal models, status enum, graph states (nodes need them → avoids graph↔nodes cycle)
    nodes.py     node functions
    graph.py     question subgraph, rfp graph
  evaluation.py  judge + categorical eval
```

## Graph design
```
rfp graph:  extract ──Send per question──► answer (try/except → question subgraph) ──► report

question subgraph:
retrieve → draft ─┬─ FAIL_MSG ──────────────────────────┐
                  └─► judge ─┬─ ok ────────────────────┤
                     ▲       │                         ├─► conflict_audit → classify_status → finalize
                     │       ├─ bad, revisions left ─► draft (with feedback)
                     │       └─ bad, none left ──────┘  (step 2: FAIL_MSG / step 6: needs_review)
```
Every path runs conflict_audit + classify_status, as the current code does. Skipping them for not_found = step-6 behaviour change, if wanted.
DataFrame removed from graph state; `report` returns `Answer` objects, `excel_io` builds the file. Each `Answer` goes back to its row by `sheet` + `row_index`, set at extraction; `excel_io.read_sheets` is the only workbook read, so `row_index` means the same in extraction and writer.
`build_answer_sheets` keeps the old `pd.concat` quirks on purpose (5a = identical Excel): every sheet gets the columns of all sheets, int IDs can become floats, sheets without rows are dropped. Fix: see Later.

## Verification (per slice)
- `.\check.ps1` (ruff + pytest), created in step 1; ruff added to requirements.
- Smoke test with `eval/fail_test.xlsx` (not in `Backend/data/`, else it gets ingested): password question answered with citation; shoe-size question = not found; colours correct (red only until step 6, then yellow too). Also: a dropdown column, a "Supported (Yes/No)" header, a second sheet without ID column.
- Smoke expectations are per step: the "Supported (Yes/No)" ID bug (duplicate IDs, overwritten answers) is expected until step 4; yellow only from step 6.
- Step 6 changes are smoke-checked only; measured later against the tag.
- Structural changes update CLAUDE.md (Map, Commands) and `start.bat` in the same commit.

## Milestones (each = ≥1 commit, app works after each)
0. Tag `v1-before-cleanup`, back up `chroma_db/`, move eval set.
1. Pure move into layout + lazy store + `check.ps1` + first tests.
2. Split agent into question subgraph, same behaviour (last judge round → FAIL_MSG).
3. Ingestion (decisions 2–4) + re-ingest.
4. Excel I/O: ID-column fix, sheet names without ID column, cost rounding, reject `.xls` (+ tests); frontend pickers drop `.xls`, add `.xlsm`, subtitles updated.
5. a) `Answer` objects replace DataFrame in state → b) `status` enum + frontend uses it → c) grammar ("I couldn't find…").
6. Agent logic, one commit each: 6.0 move prompts to `prompts.py` → past-RFP safeguards (below) → judge sees question → judge understands past-RFP Q&A rows (below) → reasoning before verdict → system/human message split → LLM-facing `AnalystDraft` (code builds `Answer`) → citation validation in code → `needs_review` instead of discard.
   **Past-RFP safeguards.** Evidence (eval run 2026-11-01, original private eval set): one answer copied another customer's name; 20 answers cite past-RFP files whose names reveal other customers; one answer copied another questionnaire's item numbering.
   a) Prompt rule: never include names of other customers/organizations or references to other questionnaires' numbering.
   b) Neutral display names for past-RFP sources in citations and the Sources column (e.g. "Past RFP response A (Row 87)"), mapped in config. Neutral names replace the whole source label (file + sheet) in the `--- SOURCE: ---` headers in retrieve and conflict_audit, so the LLM never sees real past-RFP names; real names kept internally.
   c) Later option: code check marks answers containing known customer names as `needs_review`.
   **Judge understands past-RFP Q&A rows.** A row "Question: …? Answer: Yes" supports the statement; "Answer: No" contradicts it. Evidence (original private eval set): the judge rejected a supported answer 3× although a past-RFP row answered the same question Yes → give_up → not_found.
7. English comments, remove dead code (`retrieved_context`, `draft_answer`, `nest_asyncio`), `start.bat` (English, stop only own processes), README.

## Later
- **Eval:** review eval set + add "answerable" column; fix evaluator not-found scoring; evaluator results show bare IDs and a `Q-n` fallback (display only); ~~pin judge model~~ (done: `JUDGE_MODEL` in config); baseline v1 vs current ×3 runs (mean + spread); `golden_set_v1`.
- **Agent:** intent check; Literal schema for dropdown values; validate conflict snippets in code; conflict audit reusing draft docs.
- **Evaluator:** score rows whose expected answer is not-found instead of skipping them (evidence: the reverted rule 4 change dropped not-found from ~14 to ~2 with a flat score; ~10 non-answers were invisible).
- **Citation coverage:** flag factual sentences without a citation (absence statements excepted; measure false alarms).
- **Judge model:** separate `JUDGE_MODEL` setting; A/B the current judge vs. a stronger model on the eval (cost vs. fewer wrong rejections). Evidence: gpt-4o-mini judge rejects RULE-3 absence statements inconsistently and its feedback pushes the drafter into the forbidden inference (password question, run 2).
- **Retrieval:** watch Excel rows crowding out PDF evidence (seen on the original private eval set); similarity k=5 since 2026-11-08 (decision 4). Open: chunking (EV-13: hosting sentence in an intro-heavy chunk, split across chunks), k=8 (44/46 but 2.7 past-RFP rows per question), re-measure answer scores.
- **Input:** chunk long PDF RFPs.
- **Ingestion:** skip past-answer Excel rows whose answer is a fail message (old or new). Label questionnaire columns properly (real header row instead of "Unnamed: N"; guidance columns like "Version 3.03" marked as guidance), evidence: a past-RFP questionnaire's chunks; then re-ingest it.
- **Excel output:** fix concat quirks (float IDs, union columns, dropped empty sheets).
- **Infra/API:** streaming progress / background jobs; API redesign; auth, Docker; configurable backend URL in frontend.
- **Upload:** response reports per-file status (partial failures are only in logs today).
- **Tests:** graph integration tests with mocked LLMs.
