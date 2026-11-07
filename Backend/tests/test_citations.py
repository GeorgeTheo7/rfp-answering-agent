from types import SimpleNamespace

from app.agent import nodes
from app.agent.graph import question_graph
from app.agent.nodes import check_citations, parse_citations, route_after_validation
from app.agent.schemas import (
    AnalystDraft, Answer, ConflictDetection, HallucinationEvaluation, Question, SourceRef, company_analysts,
)
from app.config import FAIL_MSG, FAIL_MSG_PREFIX, MAX_REVISIONS

PAST_RFP = "Velmora Retail Group - Vendor Security Assessment - LogistiComp WMS (2025).xlsx"
PAST_RFP_SHEET = "Assessment _ Full | Vendor Response"
ALLOWED = [
    SourceRef("LC-POL-002 Access Control and Password Policy.pdf", "", "Page 2"),
    SourceRef(PAST_RFP, PAST_RFP_SHEET, "Row 180"),
    SourceRef("past.xlsx", "", "Row 9"),
]


# --- parse_citations (real formats from eval outputs)
def test_parses_pdf_citation_with_hyphen_in_name():
    text = "Min 8 chars. [Source: LC-POL-002 Access Control and Password Policy.pdf (Page 2)]"
    assert parse_citations(text) == ["LC-POL-002 Access Control and Password Policy.pdf (Page 2)"]


def test_parses_excel_citation_with_pipes_underscores_and_sheet():
    text = f"Yes. [Source: {PAST_RFP} - {PAST_RFP_SHEET} (Row 180)]"
    assert parse_citations(text) == [f"{PAST_RFP} - {PAST_RFP_SHEET} (Row 180)"]


def test_strips_bold_markers():
    assert parse_citations("Yes. [**Source: policy.pdf (Page 1)**]") == ["policy.pdf (Page 1)"]


def test_parses_several_citations_in_a_row_and_in_one_bracket():
    text = "A. [Source: a.pdf (Page 1)][**Source: b.pdf (Page 2)**] B. [Source: c.pdf (Page 3); Source: d.xlsx (Row 4)]"
    assert parse_citations(text) == ["a.pdf (Page 1)", "b.pdf (Page 2)", "c.pdf (Page 3)", "d.xlsx (Row 4)"]


def test_citation_without_location_kept_whole():
    assert parse_citations("Yes. [Source: policy.pdf]") == ["policy.pdf"]


def test_no_citations():
    assert parse_citations("Yes, we do.") == []
    assert parse_citations(None) == []


# --- check_citations
def test_exact_labels_are_valid_ignoring_case_and_whitespace():
    cited = ["lc-pol-002 access control and password policy.pdf  (Page 2)", f"{PAST_RFP} - {PAST_RFP_SHEET} (Row 180)"]
    assert check_citations(cited, ALLOWED) == ([], [])


def test_sheet_omitted_is_valid_near_miss():
    assert check_citations([f"{PAST_RFP} (Row 180)"], ALLOWED) == ([], [f"{PAST_RFP} (Row 180)"])


def test_wrong_row_of_retrieved_file_is_invalid():
    cited = [f"{PAST_RFP} - {PAST_RFP_SHEET} (Row 181)", "LC-POL-002 Access Control and Password Policy.pdf (Page 3)"]
    assert check_citations(cited, ALLOWED) == (cited, [])


def test_unretrieved_file_is_invalid():
    assert check_citations(["LC-POL-001 Information Security Policy.pdf (Page 20)"], ALLOWED) == (["LC-POL-001 Information Security Policy.pdf (Page 20)"], [])


def test_missing_location_is_invalid():
    assert check_citations(["past.xlsx"], ALLOWED) == (["past.xlsx"], [])


# --- validate_citations_node + router
def _state(answer_text, attempt=1):
    draft = Answer(question_id="Q1", question_text="q", assigned_analyst="a", answer_text=answer_text, category="Tech")
    return {"draft": draft, "attempt": attempt, "allowed_sources": ALLOWED}


def test_valid_answer_goes_to_judge():
    result = nodes.validate_citations_node(_state("Yes. [Source: past.xlsx (Row 9)]"))
    assert result == {"citations_valid": True}
    assert route_after_validation(result) == "judge"


def test_invalid_citation_redrafts_with_feedback_listing_bad_and_allowed():
    result = nodes.validate_citations_node(_state("Yes. [Source: other.pdf (Page 1)]"))
    assert result["citations_valid"] is False
    assert "other.pdf (Page 1)" in result["feedback"]
    assert all(ref.label in result["feedback"] for ref in ALLOWED)
    assert route_after_validation({**result, "attempt": 1}) == "draft"


def test_answer_without_citation_is_invalid():
    result = nodes.validate_citations_node(_state("Yes, we do."))
    assert result["citations_valid"] is False and "no citations" in result["feedback"]


def test_no_revisions_left_gives_up():
    state = _state("Yes. [Source: other.pdf (Page 1)]", attempt=MAX_REVISIONS + 1)
    result = nodes.validate_citations_node(state)
    assert result == {"citations_valid": False, "review_note": "Invalid citations: other.pdf (Page 1) (file not retrieved)"}
    assert route_after_validation({**result, "attempt": MAX_REVISIONS + 1}) == "give_up"


# --- finalize sources_used
def test_finalize_sources_drop_location_keep_sheet():
    text = f"A. [Source: {PAST_RFP} - {PAST_RFP_SHEET} (Row 180)] B. [**Source: a.pdf (Page 1)**][Source: a.pdf (Page 2)]"
    draft = Answer(question_id="Q1", question_text="q", assigned_analyst="a", answer_text=text, category="Tech")
    allowed = ALLOWED + [SourceRef("a.pdf", "", "Page 1"), SourceRef("a.pdf", "", "Page 2")]
    answer = nodes.finalize_node({"draft": draft, "conflicts": "", "status_map": {}, "allowed_sources": allowed})["answer"]
    assert answer.sources_used == [f"{PAST_RFP} - {PAST_RFP_SHEET}", "a.pdf"]


# --- question subgraph with fake LLMs (retrieve → draft → validate_citations → judge / redraft / give_up)
def _run_subgraph(monkeypatch, drafts, judge_rejects=False):
    doc = SimpleNamespace(page_content="Min 8 chars.", metadata={"source": "policy.pdf", "file_type": "pdf", "page": 1})
    store = SimpleNamespace(as_retriever=lambda **kw: SimpleNamespace(invoke=lambda text: [doc]))
    monkeypatch.setattr(nodes, "get_vectorstore", lambda: store)

    draft_texts = iter(drafts)
    calls = {"draft": 0, "judge": 0}

    def respond(schema):
        if schema is AnalystDraft:
            calls["draft"] += 1
            return AnalystDraft(answer_text=next(draft_texts))
        if schema is HallucinationEvaluation:
            calls["judge"] += 1
            if judge_rejects:
                return HallucinationEvaluation(reasoning="no", has_hallucination=True, feedback=f"unsupported {calls['judge']}")
            return HallucinationEvaluation(reasoning="ok", has_hallucination=False, feedback="")
        assert schema is ConflictDetection
        return ConflictDetection(reasoning="none", has_conflict=False, conflict_details="")

    fake_llm = SimpleNamespace(with_structured_output=lambda schema: SimpleNamespace(invoke=lambda prompt: respond(schema)))
    monkeypatch.setattr(nodes, "_llm", lambda state: fake_llm)

    question = Question(id="[S] 1", text="Password length?", category="Security")
    result = question_graph.invoke({"question": question, "selected_model": "gpt-4o-mini",
                                    "analyst": company_analysts["Security"]})
    return result["answer"], calls


BAD = "Min 8. [Source: LC-POL-001 Information Security Policy.pdf (Page 20)]"
GOOD = "Min 8. [**Source: policy.pdf (Page 1)**]"


def test_subgraph_redrafts_after_unretrieved_citation(monkeypatch):
    answer, calls = _run_subgraph(monkeypatch, [BAD, GOOD])
    assert calls == {"draft": 2, "judge": 1}
    assert answer.answer_text == GOOD and answer.status == "answered" and answer.sources_used == ["policy.pdf"]


def test_subgraph_keeps_last_draft_for_review_when_every_citation_is_unretrieved(monkeypatch):
    answer, calls = _run_subgraph(monkeypatch, [BAD] * (MAX_REVISIONS + 1))
    assert calls == {"draft": MAX_REVISIONS + 1, "judge": 0}
    assert answer.answer_text == BAD and answer.status == "needs_review" and answer.sources_used == []
    assert answer.review_note == "Invalid citations: LC-POL-001 Information Security Policy.pdf (Page 20) (file not retrieved)"


def test_subgraph_needs_review_sources_keep_only_valid_citations(monkeypatch):
    mixed = "Min 8. [Source: policy.pdf (Page 1)] [Source: LC-POL-001 Information Security Policy.pdf (Page 20)]"
    answer, _ = _run_subgraph(monkeypatch, [mixed] * (MAX_REVISIONS + 1))
    assert answer.status == "needs_review" and answer.sources_used == ["policy.pdf"]
    assert answer.review_note == "Invalid citations: LC-POL-001 Information Security Policy.pdf (Page 20) (file not retrieved)"


def test_subgraph_judge_rejects_every_draft_needs_review_with_last_feedback(monkeypatch):
    answer, calls = _run_subgraph(monkeypatch, [GOOD] * (MAX_REVISIONS + 1), judge_rejects=True)
    assert calls == {"draft": MAX_REVISIONS + 1, "judge": MAX_REVISIONS + 1}
    assert answer.answer_text == GOOD and answer.status == "needs_review" and answer.sources_used == ["policy.pdf"]
    assert answer.review_note == f"Judge: unsupported {MAX_REVISIONS + 1}"


def test_subgraph_all_drafts_not_found_stays_not_found(monkeypatch):
    # Near-miss wording: not FAIL_MSG exactly, so it goes through validation (no citation) and give_up.
    answer, calls = _run_subgraph(monkeypatch, [FAIL_MSG_PREFIX + "."] * (MAX_REVISIONS + 1))
    assert calls == {"draft": MAX_REVISIONS + 1, "judge": 0}
    assert answer.answer_text == FAIL_MSG and answer.status == "not_found"
    assert answer.sources_used == [] and answer.review_note == ""
