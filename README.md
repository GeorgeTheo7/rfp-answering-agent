# RFP Answering Agent

Answers RFP and security questionnaires (Excel or PDF) from a knowledge base of company policy PDFs and past RFP answer spreadsheets.
Each question goes through a LangGraph subgraph: retrieve → draft with inline citations → check citations in code → LLM judge → redraft or hand off to a human.
The output is the original workbook with answers, sources, dropdown values and a status colour per row (red = not found/error, yellow = needs review).

![UI screenshot](docs/screenshot.png)

**Stack:** Python 3.12, FastAPI, LangGraph, LangChain, Chroma, OpenAI (`gpt-4o-mini` default, `text-embedding-3-small`), LlamaParse for PDFs, LangSmith tracing (optional), React/TanStack frontend.

## Architecture

### RFP graph
`extract_node` reads questions (Excel: question/ID/dropdown column detection; PDF: LLM extraction into `ExtractedQuestion`), then fans out with `Send`, one `answer_node` per question (concurrency 5). Each `answer_node` runs the question subgraph inside one try/except, so a failing question becomes `status=error` instead of failing the whole run. `report_node` orders the `Answer` objects; `excel_io` writes them back to their original sheet and row.

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	extract_node(extract_node)
	answer_node(answer_node)
	report_node(report_node)
	__end__([<p>__end__</p>]):::last
	__start__ --> extract_node;
	answer_node --> report_node;
	extract_node -.-> answer_node;
	report_node --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

### Question subgraph
Dotted arrows are router decisions. A "not found" draft skips validation and judge. Invalid citations or a judge rejection send the draft back with feedback, up to `MAX_REVISIONS = 2` (max 3 drafts); after that `give_up` keeps the last draft for a human. Every path runs the conflict audit and the dropdown classifier before `finalize` sets the status.

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	retrieve(retrieve)
	draft(draft)
	validate_citations(validate_citations)
	judge(judge)
	give_up(give_up)
	conflict_audit(conflict_audit)
	classify_status(classify_status)
	finalize(finalize)
	__end__([<p>__end__</p>]):::last
	__start__ --> retrieve;
	classify_status --> finalize;
	conflict_audit --> classify_status;
	draft -.-> conflict_audit;
	draft -.-> validate_citations;
	give_up --> conflict_audit;
	judge -.-> conflict_audit;
	judge -.-> draft;
	judge -.-> give_up;
	retrieve --> draft;
	validate_citations -.-> draft;
	validate_citations -.-> give_up;
	validate_citations -.-> judge;
	finalize --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

Both diagrams are generated from the compiled graphs with `get_graph().draw_mermaid()`.

## How it works

- **Retrieval.** Chroma, MMR with k=5, fetch_k=20, λ=0.7. The knowledge base mixes long policy PDFs with many short past-RFP rows (Excel is 463 of 745 chunks). At the default λ=0.5, MMR's diversity term dropped the policy chunks that held the answer (similarity ranks 3–4) in favour of past-RFP rows. λ=0.7 weights relevance more and keeps both.
- **Analyst draft.** A persona per category (Security/Tech/Product) writes an answer with inline `[Source: <label> (Page N | Row N)]` citations. The LLM returns `AnalystDraft` (a single `answer_text` field). Code builds the full `Answer` (IDs, sheet, row, sources, status), so the model can't change bookkeeping fields.
- **Citation validation in code.** `parse_citations` pulls the cited labels out, and `check_citations` compares them with the chunks that were actually retrieved. No citations, an unknown file or a location that wasn't retrieved → redraft with the list of allowed labels. No LLM involved.
- **LLM judge.** Sees the question, the retrieved context and the draft. It writes `reasoning` before `has_hallucination` and `feedback`. It is told how to read past-RFP rows ("Yes" supports the claim in that row's question, "No" contradicts it, guidance text is not evidence). Absence vs. inference rule: "the context does not specify X" is valid, while "X is implied to be 8" is a hallucination unless the context says so.
- **Redraft.** The analyst gets its previous answer plus the judge's feedback and is told to fix only the flagged claims. Supported content stays.
- **`needs_review` instead of discarding.** When revisions run out, the last draft is kept with a `review_note` (last judge feedback or invalid citations) and shows yellow. Before this change it was replaced by the "not found" message. Answers that are partly supported and partly "not found" are flagged the same way.
- **Status enum.** `answered | not_found | needs_review | error` is set by code in `finalize` and the error fallback. It drives the UI and Excel colours. A human edit in the UI sets `answered`.
- **Ingestion dedup.** Files are identified by filename and versioned by a SHA-256 of their bytes, stored in chunk metadata together with `chunk_count`. Same hash and complete → skip. Same hash but incomplete → re-ingest. New hash → ingest the new version first and delete the old chunks only after that succeeds, so a failed replace never loses the old version. Startup and upload use the same `ingest()`.

## Evaluation

*All numbers below were measured on the original private knowledge base and eval set, not on the LogistiComp demo data.*

**Method.** An eval set of 47 questions with expected answers. The evaluator runs the agent and has an LLM judge score each answer 0–100 against the expected one (dropdown columns are compared as exact category matches). Rows whose expected answer is "not found" are skipped, so n=33 are scored. A repeat run with nothing changed differed by ~5 points, so a setting is judged on the average of ≥2 runs, not on one run.

**Results.** Full run log: [eval/RESULTS.md](eval/RESULTS.md).
- Data mattered more than prompts. Adding two past-RFP answer spreadsheets to the 18 policy PDFs raised the score from 50.6 to 73.8; rows whose answer comes from those spreadsheets went from 27.2 to 72.5. It also exposed leaks: another customer's name was copied into an answer, and 20 citations named customer files. Safeguards are not implemented yet (see Roadmap).
- The answer-quality changes described in "How it works" (judge sees the question, reasoning before verdict, citation validation, `needs_review`, λ=0.7) averaged 74.1 over two runs against 71.5 before: +2.6, inside the ±5 noise. Individual wins repeated: the password-length question went from 0 to 90 in both runs.
- One prompt change looked neutral by score but was a regression; see "A flat score hiding a regression" below.

**Known limitations.**
- Expected answers are old agent outputs that nobody has reviewed (several rows are known to be wrong), so the score measures agreement with the agent's first version, not accuracy.
- Rows with an expected "not found" are skipped, so the evaluator can't see an agent that answers questions it shouldn't.
- Judge: gpt-6-luna, reasoning effort low. It is an alias with no dated snapshot, so OpenAI can change it under us; one judge model only. The eval set is small.

## Engineering notes

- **A docstring sent to the LLM.** A developer docstring on the Pydantic draft model became the JSON-schema description the model saw. On one question (password length), drafts over-claimed "minimum 8" in 26/26 runs with the docstring and 0/30 without it (runs interleaved). Fix: a comment instead of a docstring, plus snapshot tests over prompts and LLM-facing schemas (`tests/prompt_snapshots/`), so any byte change to what the model sees shows up in review.
- **Judge contradicting itself.** With the verdict field first, the judge flagged a supported claim as unsupported, and its feedback quoted the context text that supports it. Fix: a `reasoning` field before `has_hallucination`, so the verdict follows the analysis. After the change the same answer was approved.
- **MMR dropping the answer.** The password-length question kept failing. A retrieval diagnostic using the full question text showed the answer chunks at similarity ranks 3–4, removed by MMR λ=0.5 in favour of near-duplicate past-RFP rows. Fix: λ=0.7, checked offline first (both kinds of source returned), then in the eval, together with the judge changes: the question went from 0 to 90 in both runs.
- **A flat score hiding a regression.** A prompt change told the analyst to use the "not found" message only when nothing in the context was relevant. "Not found" answers fell from about 14 to 2 and the score stayed flat, which looked like a win. Checking the rows showed that about 10 of the 14 unanswerable questions now got padded partial answers. The score couldn't see it because the evaluator skips rows whose expected answer is "not found". Fix: reverted the prompt and handled partial answers in code (`is_partial_fail_text` → `needs_review` with a note). Scoring those rows is on the roadmap.

## Run it

### Run with Docker

Needs Docker Desktop and a root `.env` with `OPENAI_API_KEY` and `LLAMA_CLOUD_API_KEY` (`NAME=value` lines, no quotes).

```powershell
docker compose up --build   # frontend localhost:8080, backend localhost:8000 (/docs)
docker compose down         # stop
```

`Backend/data` and `Backend/chroma_db` are mounted from the host: new files in `data/` are ingested on startup, unchanged ones skipped. Don't run `start.bat` and compose at the same time (same ports, same Chroma store).

### Run locally

Windows, PowerShell, Python 3.12, Node.

```powershell
python -m venv venv; .\venv\Scripts\activate
pip install -r Backend/requirements.txt
cd Frontend; npm install; cd ..
# root .env: OPENAI_API_KEY, LLAMA_CLOUD_API_KEY
# optional LangSmith tracing: LANGSMITH_TRACING=true, LANGSMITH_API_KEY, LANGSMITH_PROJECT
#   LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com for EU accounts (must match the key's region)
#   (smoke.py, run_rfp.py, compare_excel.py switch tracing off)
.\start.bat                          # backend :8000, frontend :8080; ingests new files in Backend/data/ on startup
.\check.ps1                          # ruff (F rules) + pytest, no LLM or network calls
.\venv\Scripts\python eval\smoke.py --step 6   # real LLM calls (<$0.01) on eval/fail_test.xlsx, PASS/FAIL per eval/SMOKE.md
```

Other tools: `eval\run_rfp.py <file>` (any RFP through the pipeline, prints the agent log), `eval\compare_excel.py` (export vs. recorded baseline, cell by cell).

## Project layout

```
docker-compose.yml   backend + frontend services
Backend/Dockerfile   python:3.12-slim, uvicorn on :8000
Backend/app/
  main.py         FastAPI app, startup ingest, CORS
  api.py          endpoints (analyze, export edits, upload, evaluate)
  config.py       paths, retrieval params, FAIL_MSG, pricing (no side effects)
  store.py        lazy Chroma singleton
  ingestion.py    loaders + shared ingest() with hash dedup
  excel_io.py     column detection, dropdowns, read_sheets, formatted writer
  evaluation.py   LLM judge + categorical eval
  agent/
    prompts.py    all prompt builders (pinned by snapshot tests)
    schemas.py    pydantic models, Status enum, graph states
    nodes.py      node functions + routers
    graph.py      question subgraph, rfp graph
Backend/tests/    pytest: pure functions, citations, ingest dedup on a temp Chroma, prompt snapshots
eval/             eval set, smoke test, debug runner, Excel comparison, RESULTS.md
Frontend/src/components/   RfpSolver, KnowledgeBase, AccuracyEvaluator
Frontend/Dockerfile  node build → nginx; nginx.conf serves the SPA shell
docs/SPEC.md      design decisions with evidence, roadmap
```

## Roadmap

- **Eval:** review the eval set and add an "answerable" column; score not-found rows instead of skipping them; pin the judge model; first version vs. current over 3 runs (mean + spread).
- **Past-RFP safeguards:** prompt rule against copying other customers' names or other questionnaires' numbering; neutral display names for past-RFP sources in context and citations; code check that flags known customer names as `needs_review`.
- **Judge model:** separate `JUDGE_MODEL` setting; A/B `gpt-4o-mini` against a stronger judge (it rejects valid absence statements inconsistently).
- **Judge rules:** allow direct deductions (e.g. 12 months ≥ 3 months), forbid speculation.
- **Citations:** claim-level check, meaning every factual sentence must carry a citation that supports it (absence statements excepted).
- **Agent:** Literal schema for dropdown values; validate conflict-audit snippets in code.
- **Ingestion:** skip past-RFP rows whose answer is a fail message; use real header rows for questionnaire columns.
- **Tests:** graph integration tests with mocked LLMs.
- **Infra:** streaming progress / background jobs, auth, Docker, configurable backend URL.
