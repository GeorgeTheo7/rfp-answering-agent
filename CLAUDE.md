# CLAUDE.md

## Rules
- Be extremely concise in all interactions, plans and commit messages. Sacrifice grammar for concision.
- Don't use the AskUserQuestion tool.
- When I ask a question or say "don't implement yet": answer/propose only, change nothing.
- I'm learning: if I say "explain", explain properly.
- One small change per conversation and per commit. Suggest an imperative commit message.
- Never read or modify `.env`.
- Solo repo: commit directly on main; don't create branches unless I ask.

## Project
Answers RFP/security questionnaires (Excel/PDF) with RAG over company policy PDFs.
Backend: FastAPI + LangGraph (Python 3.12). Frontend: React/TanStack (Lovable-generated). `Backend/data/` holds fictional LogistiComp demo documents (committed on purpose). Greek only in column-header keywords (`"ερώτηση"`, `"α/α"`, …) so Greek RFPs work — keep them.

## Commands (Windows, PowerShell)
- Run all: `.\start.bat` (backend :8000, frontend :8080). Stop with the VS Code terminal trash icon; a keypress in start.bat kills ALL python/node processes.
- Backend: `cd Backend; ..\venv\Scripts\activate; python -m uvicorn app.main:app --reload`
- Install: `pip install -r Backend/requirements.txt` (venv at `./venv`)
- Check: `.\check.ps1` (ruff F rules + pytest on Backend; non-zero exit on failure)
- Smoke: `.\venv\Scripts\python eval\smoke.py --step <N>` (real LLM calls on `eval/fail_test.xlsx`, PASS/FAIL per `eval/SMOKE.md`)
- Compare: `.\venv\Scripts\python eval\compare_excel.py [--no-llm]` (exports vs `eval/baseline/`, see `eval/SMOKE.md`)
- Prompt snapshots, after an intended prompt change: `cd Backend; ..\venv\Scripts\python -m tests.test_prompts` (rewrites `tests/prompt_snapshots/`; review the diff)
- Frontend (`Frontend/`): `npm run dev | build | lint`
- Env vars in root `.env`: `OPENAI_API_KEY`, `LLAMA_CLOUD_API_KEY`

## Map
- `Backend/app/`: package; imports are `from app.x import ...` (run from `Backend/`). `data/`, `chroma_db/`, `tests/` stay in `Backend/`.
- `Backend/app/config.py`: paths (BASE_DIR = Backend/, CHROMA_DIR, DATA_DIR), COLLECTION_NAME, EXCEL_EXTENSIONS, FAIL_MSG, OLD_FAIL_MSG_PREFIX, RETRIEVAL_SEARCH_TYPE (similarity | mmr), RETRIEVAL_K, RETRIEVAL_FETCH_K + MMR_LAMBDA (mmr only), DEFAULT_AGENT_MODEL (gpt-6-luna; API + UI default), MODEL_SETTINGS (per-model ChatOpenAI settings for agent + judge, via `nodes.chat_model`; gpt-6-luna = effort low, no temperature), JUDGE_MODEL (evaluator judge only; default gpt-6-luna: alias, no dated snapshot), MODEL_PRICING, COST_DECIMALS. No side effects.
- `Backend/app/store.py`: lazy Chroma singleton, `get_vectorstore()`.
- `Backend/app/main.py`: FastAPI app, lifespan (startup ingest of new files in data/), CORS, includes `api.router`.
- `Backend/app/ingestion.py`: loaders, shared `ingest()` (per-file writes; failed write raises `IngestWriteError`), `ingest_local_directory`.
- `Backend/app/excel_io.py`: `find_id_column`/`resolve_id_column` (duplicate IDs → row IDs), `find_question_column`, `read_sheets` (only workbook read), dropdown detection, `build_answer_sheets` (Answers → sheets), formatted Excel writer (colours the `Answer` column by status), `parse_question_id`.
- `Backend/app/agent/prompts.py`: all prompt builders (strings in, string out; whitespace is prompt text). Pinned byte-exact by `tests/test_prompts.py` + `tests/prompt_snapshots/`.
- `Backend/app/agent/schemas.py`: pydantic models, analyst data (name, role, tone), graph states.
- `Backend/app/agent/nodes.py`: node functions (extract, report; question subgraph: retrieve, draft, validate_citations (+ pure `parse_citations`), judge, give_up (keeps last draft as needs_review), conflict_audit, classify_status, finalize + routers), cost.
- `Backend/app/agent/graph.py`: builds `question_graph`, `answer_question_node` (try/except + cost callback around it), `rfp_graph`.
- `Backend/app/evaluation.py`: LLM judge + categorical eval.
- `Backend/app/api.py`: endpoints on `router` (upload calls `ingest()`; 502 on `IngestWriteError`; `.xls` → 400; preview rows from `final_answers`), evaluator endpoint.
- `Frontend/src/components/`: RfpSolver, KnowledgeBase, AccuracyEvaluator. Backend URL hardcoded. `routeTree.gen.ts` generated, don't edit.

## Contracts (change one place → update all)
- Question IDs `"[<sheet>] <id>"`: built at extraction, sent as preview `id` (shown in the UI), parsed in `/api/rfp/export_edits`.
- `Status` (`answered | not_found | needs_review | error`): set in `finalize_node` (via `is_fail_text`; `needs_review` = draft has a `review_note`, or fail text + other content (partial, note added)) and the error fallback; sent as preview `status`, back through `FullRow`; colours UI (`ANSWER_STATUS_CLASSES` in RfpSolver.tsx) and Excel (`STATUS_FILLS`). Red = not_found/error, yellow = needs_review. UI edit → `answered`.
- `FAIL_MSG` / `FAIL_MSG_PREFIX` text: LLM's "found nothing" signal (`is_fail_text`, `route_after_draft`, `finalize_node` sources); also written by `draft_node` when `AnalystDraft.answer_found` is false (model's own text kept in `review_note` with `OVERRIDE_NOTE_PREFIX`; text checks stay as fallback), evaluator's expected answers (via `is_fail_text`), persona rule + evaluation judge in `prompts.py`. Never for colours. `OLD_FAIL_MSG_PREFIX` = pre-5c wording in old files: recognised by `is_fail_text`, never written.
- `review_note` (why a `needs_review` draft was rejected: last judge feedback or invalid citations, or partial not-found; on a `not_found` answer only the answer_found override note): set in `give_up_node` and `draft_node` (override), partial note appended in `finalize_node`; preview `review_note`, back through `FullRow`; Excel "Review note" column (`REVIEW_NOTE_COL`, only when some answer has one); UI edit clears it. Invalid citations only there, never in `sources_used`.
- `sheet` + `row_index` on `Question`/`Answer` place an answer in its row: set at extraction from `read_sheets`, copied in `finalize_node` and the error fallback in `graph.py`.

## Known issues (not rules)
- Excel export keeps `pd.concat` quirks on purpose (float IDs, union columns, dropped empty sheets); see SPEC Later.
- Evaluator results show bare IDs and a `Q-n` fallback (display only).
- Unmatched categories default to "Product".
- Old unused `chroma_db/` at repo root.