import json
import re
from typing import List, Dict

import pandas as pd
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_community.document_loaders import PyMuPDFLoader
from langgraph.types import Send

from app.config import (
    DEFAULT_AGENT_MODEL, EXCEL_EXTENSIONS, FAIL_MSG, FAIL_MSG_PREFIX, MAX_REVISIONS, MMR_LAMBDA, MODEL_PRICING, MODEL_SETTINGS, OLD_FAIL_MSG_PREFIX,
    RETRIEVAL_FETCH_K, RETRIEVAL_K, RETRIEVAL_SEARCH_TYPE,
)
from app.store import get_vectorstore
from app.excel_io import detect_status_columns, find_question_column, is_id_header, read_sheets, resolve_id_column
from app.agent.prompts import (
    analyst_draft_prompt, citation_feedback, conflict_audit_prompt, hallucination_judge_prompt, pdf_extraction_prompt,
    persona_rules, status_classifier_prompt,
)
from app.agent.schemas import (
    SourceRef, Status, StatusSpec, Question, RFPQuestions, AnalystDraft, Answer, StatusChoices, ConflictDetection,
    HallucinationEvaluation, QuestionState, RFPGraphState,
)

# ==========================================
# 1. SETUP
# ==========================================
load_dotenv()

def chat_model(model_name: str, timeout: int) -> ChatOpenAI:
    """Every LLM client (agent and evaluator judge): the model with its MODEL_SETTINGS."""
    if model_name not in MODEL_SETTINGS:
        raise ValueError(f"Unknown model {model_name!r}; add it to MODEL_SETTINGS in config.py")
    return ChatOpenAI(model=model_name, max_retries=5, timeout=timeout, **MODEL_SETTINGS[model_name])

def calculate_cost(model_name: str, cb) -> float:
    """Single source of truth for token cost.
    If the model is not in MODEL_PRICING, falls back to cb.total_cost."""
    if model_name in MODEL_PRICING:
        price_in, price_out = MODEL_PRICING[model_name]
        return (cb.prompt_tokens * price_in / 1_000_000) + (cb.completion_tokens * price_out / 1_000_000)
    return cb.total_cost

# ==========================================
# 3b. CONSTRAINED STATUS CLASSIFIER (dropdown columns)
# ==========================================
def _canonical_value(chosen: str, allowed_values: List[str]) -> str:
    """Returns the official (verbatim) value from allowed_values, or "" if none matches."""
    chosen = (chosen or "").strip()
    for v in allowed_values:
        if chosen.lower() == v.strip().lower():
            return v
    for v in allowed_values:
        if chosen and (chosen.lower() in v.lower() or v.lower() in chosen.lower()):
            return v
    return ""

def classify_statuses(question: "Question", answer_text: str, specs: List["StatusSpec"], model_name: str) -> Dict[str, str]:
    """Maps the detailed answer to ONE value for EVERY dropdown column.
    A single LLM call for ALL columns. Returns {column_header: chosen_value}."""
    if not specs:
        return {}
    valid_map = {s.column: s.allowed_values for s in specs}

    llm = chat_model(model_name, timeout=60)
    classifier = llm.with_structured_output(StatusChoices)
    result = classifier.invoke(status_classifier_prompt(question.text, answer_text, specs))

    out = {}
    for ch in result.choices:
        # Resolve the column header (verbatim, else case-insensitive)
        allowed = valid_map.get(ch.column)
        target_col = ch.column
        if allowed is None:
            for col, av in valid_map.items():
                if (ch.column or "").strip().lower() == col.strip().lower():
                    allowed, target_col = av, col
                    break
        if allowed is None:
            continue
        canon = _canonical_value(ch.chosen_value, allowed)
        if canon:
            out[target_col] = canon
    return out

# ==========================================
# 5. GRAPH NODES
# ==========================================
def extract_questions_node(state: RFPGraphState):
    input_path = state["rfp_input_path"]
    chosen_model = state.get("selected_model", DEFAULT_AGENT_MODEL)
    print(f"\n--- [NODE] READING QUESTIONS FROM: {input_path} (Model: {chosen_model}) ---")
    questions = []

    if input_path.lower().endswith(EXCEL_EXTENSIONS):
        all_sheets = read_sheets(input_path)
        status_map = detect_status_columns(input_path)  # {sheet: [ {column, allowed_values}, ... ]}
        
        for sheet_name, df in all_sheets.items():
            sheet_specs = [StatusSpec(column=s["column"], allowed_values=s["allowed_values"])
                           for s in status_map.get(sheet_name, [])]
            col_map = {str(c).lower().strip(): c for c in df.columns}
            q_col = find_question_column(df.columns)

            if q_col is None:
                q_col = next((c for c in df.columns if not is_id_header(c)), None)
                if q_col is None: continue

            id_col = resolve_id_column(df, sheet_name)
            cat_col = next((v for k, v in col_map.items() if "category" in k or "κατηγορία" in k), None)
            
            for index, row in df.iterrows():
                text = str(row[q_col])
                if text == "nan" or not text.strip(): continue
                    
                raw_id = str(row[id_col]) if id_col and pd.notna(row[id_col]) else f"Q{index+1}"
                q_id_with_sheet = f"[{sheet_name}] {raw_id}"
                
                category = "Product" 
                if cat_col and pd.notna(row[cat_col]):
                    cat_val = str(row[cat_col]).lower()
                    if "sec" in cat_val or "ciso" in cat_val: category = "Security"
                    elif "tech" in cat_val or "arch" in cat_val: category = "Tech"
                    else: category = "Product"
                else:
                    text_lower = text.lower()
                    if any(w in text_lower for w in ["security", "auth", "login", "password", "cyber", "compliance", "policy", "encryption", "keys"]): category = "Security"
                    elif any(w in text_lower for w in ["api", "architecture", "database", "cloud", "server", "integration", "migration"]): category = "Tech"

                questions.append(Question(
                    id=q_id_with_sheet,
                    text=text,
                    category=category,
                    status_specs=sheet_specs,
                    sheet=sheet_name,
                    row_index=index,
                ))
            
    elif input_path.lower().endswith('.pdf'):
        loader = PyMuPDFLoader(input_path)
        docs = loader.load()
        full_text = "\n".join([doc.page_content for doc in docs])
        dynamic_llm = chat_model(chosen_model, timeout=120)
        structured_llm = dynamic_llm.with_structured_output(RFPQuestions)
        result = structured_llm.invoke(pdf_extraction_prompt(full_text))
        # PDFs have no dropdown columns or rows -> system fields keep their defaults.
        questions = [Question(id=q.id, text=q.text, category=q.category) for q in result.questions]
    else:
        raise ValueError("Unsupported file type!")
        
    print(f"   ✓ Extracted {len(questions)} questions in total.")
    return {"extracted_questions": questions}

# ==========================================
# 5b. QUESTION SUBGRAPH NODES (one question: RAG + judge loop + conflict audit)
# Wired in graph.py.
# ==========================================
def _llm(state: QuestionState) -> ChatOpenAI:
    return chat_model(state["selected_model"], timeout=90)

def retriever_settings() -> dict:
    """as_retriever() arguments of the draft retriever, from RETRIEVAL_SEARCH_TYPE."""
    if RETRIEVAL_SEARCH_TYPE == "similarity":
        return {"search_type": "similarity", "search_kwargs": {"k": RETRIEVAL_K}}
    if RETRIEVAL_SEARCH_TYPE == "mmr":
        return {"search_type": "mmr",
                "search_kwargs": {"k": RETRIEVAL_K, "fetch_k": RETRIEVAL_FETCH_K, "lambda_mult": MMR_LAMBDA}}
    raise ValueError(f"RETRIEVAL_SEARCH_TYPE must be 'similarity' or 'mmr', not {RETRIEVAL_SEARCH_TYPE!r}")

def retrieve_node(state: QuestionState):
    question = state["question"]
    print(f"--- [NODE] ANALYST & JUDGE: Answering {question.id} ---")
    docs = get_vectorstore().as_retriever(**retriever_settings()).invoke(question.text)

    context_parts, allowed_sources = [], []
    for doc in docs:
        src = doc.metadata.get("source", "Unknown")
        file_type = doc.metadata.get("file_type", "pdf")

        if file_type == "excel":
            ref = SourceRef(src, doc.metadata.get("sheet", ""), f"Row {doc.metadata.get('row', 'Unknown')}")
        else:
            ref = SourceRef(src, "", f"Page {doc.metadata.get('page', 'Unknown')}")

        allowed_sources.append(ref)
        context_parts.append(f"--- SOURCE: {ref.label} ---\n{doc.page_content}")

    return {"context_text": "\n\n".join(context_parts), "allowed_sources": allowed_sources, "attempt": 0, "feedback": ""}

OVERRIDE_NOTE_PREFIX = "Model text before not-found override: "

def draft_node(state: QuestionState):
    question, analyst = state["question"], state["analyst"]
    context_text, feedback = state["context_text"], state["feedback"]
    persona = persona_rules(analyst.name, analyst.role_description, analyst.tone)
    previous_answer = state["draft"].answer_text if feedback else ""
    final_prompt = analyst_draft_prompt(persona, question.text, context_text, feedback, previous_answer)

    result = _llm(state).with_structured_output(AnalystDraft).invoke(final_prompt)
    answer_text, review_note = result.answer_text, ""
    if not result.answer_found:
        # The model says nothing in the context answers the question: FAIL_MSG -> route_after_draft and
        # finalize_node treat it as not_found. Its own wording is kept in the review note (unless it already
        # was just the not-found message).
        if not (is_fail_text(answer_text) and not is_partial_fail_text(answer_text)):
            review_note = f"{OVERRIDE_NOTE_PREFIX}{answer_text}"
            print(f"   [!] Attempt {state['attempt'] + 1}: answer_found=false -> FAIL_MSG. {review_note}")
        answer_text = FAIL_MSG
    draft = Answer(
        question_id=question.id,
        question_text=question.text,
        assigned_analyst=analyst.name,
        answer_text=answer_text,
        category=question.category,
        sheet=question.sheet,
        row_index=question.row_index,
        review_note=review_note,
    )
    return {"draft": draft, "attempt": state["attempt"] + 1}

_CITATION_GROUP = re.compile(r"\[([^\[\]]*Source:[^\[\]]*)\]", re.IGNORECASE)
_LABEL = re.compile(r".+?\((?:Page|Row)\b[^)]*\)", re.IGNORECASE)
_LOCATION_SUFFIX = re.compile(r"\s*\((?:Page|Row)\b[^)]*\)$", re.IGNORECASE)

def parse_citations(text: str) -> List[str]:
    """Labels cited as [Source: <label>] (bold markers removed), in order. A label ends at its
    (Page N) / (Row N); several may share one bracket. A citation without a location is kept whole."""
    labels = []
    for group in _CITATION_GROUP.findall(text or ""):
        body = re.sub(r"Source:", "", group.replace("**", ""), flags=re.IGNORECASE)
        end = 0
        for m in _LABEL.finditer(body):
            labels.append(m.group().strip(" ,;"))
            end = m.end()
        tail = body[end:].strip(" ,;")
        if tail:
            labels.append(tail)
    return labels

def _norm(label: str) -> str:
    return " ".join(label.split()).casefold()

def check_citations(citations: List[str], allowed: List[SourceRef]) -> tuple[List[str], List[str]]:
    """(bad, near_misses). Valid: exact label, or same file + location with the sheet omitted (near-miss)."""
    exact = {_norm(ref.label) for ref in allowed}
    sheetless = {_norm(f"{ref.file} ({ref.location})") for ref in allowed if ref.sheet}
    bad, near_misses = [], []
    for c in citations:
        if _norm(c) in exact:
            continue
        (near_misses if _norm(c) in sheetless else bad).append(c)
    return bad, near_misses

def _bad_reason(citation: str, allowed: List[SourceRef]) -> str:
    """For logs and the review note."""
    retrieved_file = any(_norm(citation).startswith(_norm(ref.file)) for ref in allowed)
    return "location not retrieved" if retrieved_file else "file not retrieved"

def validate_citations_node(state: QuestionState):
    draft, attempt, allowed = state["draft"], state["attempt"], state["allowed_sources"]
    citations = parse_citations(draft.answer_text)
    bad, near_misses = check_citations(citations, allowed)
    for c in near_misses:
        print(f"   [~] Attempt {attempt}: Citation near-miss (sheet omitted) -> {c}")
    if citations and not bad:
        return {"citations_valid": True}

    problems = "; ".join(f"{c} ({_bad_reason(c, allowed)})" for c in bad) or "no citation"
    print(f"   [!] Attempt {attempt}: Invalid citations -> {problems}")
    result = {"citations_valid": False, "review_note": f"Invalid citations: {problems}"}
    if attempt <= MAX_REVISIONS:
        result["feedback"] = citation_feedback(bad, [ref.label for ref in allowed])
    return result

def judge_node(state: QuestionState):
    context_text, draft, attempt = state["context_text"], state["draft"], state["attempt"]
    judge_prompt = hallucination_judge_prompt(state["question"].text, context_text, draft.answer_text)

    eval_result = _llm(state).with_structured_output(HallucinationEvaluation).invoke(judge_prompt)

    if not eval_result.has_hallucination:
        print(f"   [✓] Attempt {attempt}: Answer Approved by Judge. | Reasoning: {eval_result.reasoning}")
        return {"has_hallucination": False}
    print(f"   [!] Attempt {attempt}: Hallucination Detected -> {eval_result.feedback} | Reasoning: {eval_result.reasoning}")
    result = {"has_hallucination": True, "review_note": f"Judge: {eval_result.feedback}"}
    if attempt <= MAX_REVISIONS:
        result["feedback"] = eval_result.feedback
    return result

def give_up_node(state: QuestionState):
    """Keeps the last draft for a human (needs_review), with the last rejection reason as review note.
    A last draft that says nothing was found stays not_found."""
    draft = state["draft"]
    if is_fail_text(draft.answer_text):
        print(f"   [!] Attempt {state['attempt']}: Max revisions reached. Last draft found nothing.")
        return {"draft": draft.model_copy(update={"answer_text": FAIL_MSG, "sources_used": []})}
    print(f"   [!] Attempt {state['attempt']}: Max revisions reached. Keeping last draft for review.")
    return {"draft": draft.model_copy(update={"review_note": state["review_note"]})}

def route_after_draft(state: QuestionState) -> str:
    return "conflict_audit" if state["draft"].answer_text.strip() == FAIL_MSG else "validate_citations"

def route_after_validation(state: QuestionState) -> str:
    if state["citations_valid"]:
        return "judge"
    return "draft" if state["attempt"] <= MAX_REVISIONS else "give_up"

def route_after_judge(state: QuestionState) -> str:
    if not state["has_hallucination"]:
        return "conflict_audit"
    return "draft" if state["attempt"] <= MAX_REVISIONS else "give_up"

def conflict_audit_node(state: QuestionState):
    question = state["question"]
    # Targeted similarity retriever for conflicts
    conflict_retriever = get_vectorstore().as_retriever(search_type="similarity", search_kwargs={"k": 6})
    conflict_docs = conflict_retriever.invoke(question.text)
    conflict_parts = []
    for doc in conflict_docs:
        src = doc.metadata.get("source", "Unknown")
        file_type = doc.metadata.get("file_type", "pdf")
        if file_type == "excel":
            row_num = doc.metadata.get("row", "Unknown")
            sheet_name = doc.metadata.get("sheet", "")
            source_tag = f"{src} - {sheet_name} (Row {row_num})" if sheet_name else f"{src} (Row {row_num})"
        else:
            page = doc.metadata.get("page", "Unknown")
            source_tag = f"{src} (Page {page})"
        conflict_parts.append(f"--- SOURCE: {source_tag} ---\n{doc.page_content}")

    conflict_context_text = "\n\n".join(conflict_parts)

    conflict_prompt = conflict_audit_prompt(question.text, conflict_context_text)

    conflict_eval = _llm(state).with_structured_output(ConflictDetection).invoke(conflict_prompt)
    return {"conflicts": conflict_eval.conflict_details if conflict_eval.has_conflict else ""}

def classify_status_node(state: QuestionState):
    """Constrained classification of Excel dropdown columns; no LLM call without specs."""
    question = state["question"]
    status_map = {}
    if question.status_specs:
        try:
            status_map = classify_statuses(
                question=question,
                answer_text=state["draft"].answer_text,
                specs=question.status_specs,
                model_name=state["selected_model"],
            )
        except Exception as e:
            # A classification failure does NOT break the answer — leave it empty.
            print(f"   [!] Status classification failed for {question.id}: {e}")
            status_map = {}
    return {"status_map": status_map}

def is_fail_text(text: str) -> bool:
    """True if the text says nothing was found. Prefix, not equality: near-misses of FAIL_MSG count too.
    The old wording counts as well: it is still in old files and in past answers the LLM may copy."""
    text = text or ""
    return FAIL_MSG_PREFIX in text or OLD_FAIL_MSG_PREFIX in text

# A not-found sentence (either wording, any ending) plus the optional "Please provide a human..." tail.
_FAIL_SENTENCE = re.compile(
    rf"(?:{re.escape(FAIL_MSG_PREFIX)}|{re.escape(OLD_FAIL_MSG_PREFIX)})[^.!?]*[.!?]?"
    rf"(?:\s*{re.escape(FAIL_MSG.removeprefix(FAIL_MSG_PREFIX + '. '))})?"
)
PARTIAL_NOTE = "Partial answer: the model also used the not-found message"

# Free-worded "information is missing" statements (e.g. gpt-6-luna's paraphrased refusals). Matched on the
# answer without its citations. Bare "not available / not provided" and "no data" are left out: they usually
# state facts ("on-premises is not available"), not missing information.
_INFO_VERBS = (r"mentioned|stated|specified|described|documented|addressed|covered|detailed|indicated|defined|"
               r"referenced|included|listed")
ABSENCE_PATTERNS = [
    rf"\bnot (?:explicitly |specifically |directly |clearly )?(?:{_INFO_VERBS})\b",
    r"\b(?:does|do|did)(?: not|n't) (?:explicitly |specifically |directly |clearly )?"
    r"(?:mention|state|specify|describe|document|address|cover|detail|indicate|define|reference|include|list|provide)\b",
    r"\bno (?:specific |explicit |further |additional |detailed )?(?:information|details|mention|reference)\b",
    r"\bnot (?:available|provided|found|included) in the (?:context|documentation|documents|sources|provided|available)",
    r"\b(?:unable to|cannot|can't|could not) (?:find|confirm|determine|verify)\b",
]
_ABSENCE = re.compile("|".join(f"(?:{p})" for p in ABSENCE_PATTERNS), re.IGNORECASE)
ABSENCE_NOTE = "The answer states that information is missing; please confirm."

def has_absence_statement(text: str) -> bool:
    """True if the answer (citations removed) says some information is not in the sources."""
    return bool(_ABSENCE.search(_CITATION_GROUP.sub("", text or "")))

def is_partial_fail_text(text: str) -> bool:
    """True if the text has the not-found message AND other content (a partial answer)."""
    return is_fail_text(text) and bool(re.search(r"\w", _FAIL_SENTENCE.sub("", text)))

def finalize_node(state: QuestionState):
    """Builds the final Answer; sources_used rebuilt from the valid inline citations (invalid ones
    are only in the review note). Status: needs_review (partial not-found answer, an absence statement,
    or give_up kept the draft), not_found (only the not-found message), else answered. Cost is set by
    the caller."""
    draft = state["draft"]
    if draft.answer_text.strip() == FAIL_MSG:
        sources_used = []
    else:
        citations = parse_citations(draft.answer_text)
        bad, _ = check_citations(citations, state["allowed_sources"])
        cited = {_LOCATION_SUFFIX.sub("", c) for c in citations if c not in bad}
        sources_used = sorted(c for c in cited if c)

    review_note = draft.review_note
    if is_partial_fail_text(draft.answer_text):
        status = Status.needs_review
        review_note = f"{review_note}\n{PARTIAL_NOTE}" if review_note else PARTIAL_NOTE
    elif is_fail_text(draft.answer_text):
        status = Status.not_found
    else:
        if has_absence_statement(draft.answer_text):
            review_note = f"{review_note}\n{ABSENCE_NOTE}" if review_note else ABSENCE_NOTE
        status = Status.needs_review if review_note else Status.answered
    answer = draft.model_copy(update={
        "conflicts": state["conflicts"],
        "status_values_json": json.dumps(state["status_map"], ensure_ascii=False),
        "sources_used": sources_used,
        "status": status,
        "review_note": review_note,
    })
    return {"answer": answer}

def route_questions(state: RFPGraphState):
    questions = state.get("extracted_questions", [])
    model_name = state.get("selected_model", DEFAULT_AGENT_MODEL)
    return [Send("answer_node", {"question": q, "selected_model": model_name}) for q in questions]

def generate_final_report_node(state: RFPGraphState):
    """Puts the answers in output order: Excel = extraction order, PDF = by question ID."""
    answers = state.get("completed_answers", [])
    if state["rfp_input_path"].lower().endswith(EXCEL_EXTENSIONS):
        order = {(q.sheet, q.row_index): i for i, q in enumerate(state["extracted_questions"])}
        return {"final_answers": sorted(answers, key=lambda ans: order[(ans.sheet, ans.row_index)])}
    return {"final_answers": sorted(answers, key=lambda ans: ans.question_id)}
