from types import SimpleNamespace

import pytest

from app.agent import nodes
from app.agent.nodes import _canonical_value
from app.agent.schemas import AnalystDraft, Answer, HallucinationEvaluation, Question, Status, company_analysts
from app.config import FAIL_MSG, FAIL_MSG_PREFIX, MMR_LAMBDA, RETRIEVAL_FETCH_K, RETRIEVAL_K

ALLOWED = ["Yes", "No", "Partially Supported"]


def test_exact_match_ignores_case_and_whitespace():
    assert _canonical_value("  yes ", ALLOWED) == "Yes"


def test_substring_falls_back_to_allowed_value():
    assert _canonical_value("partially", ALLOWED) == "Partially Supported"


def test_no_match_returns_empty():
    assert _canonical_value("Maybe", ALLOWED) == ""


def test_empty_or_none_returns_empty():
    assert _canonical_value("", ALLOWED) == ""
    assert _canonical_value(None, ALLOWED) == ""


@pytest.mark.parametrize("search_type,expected", [
    ("similarity", {"search_type": "similarity", "search_kwargs": {"k": RETRIEVAL_K}}),
    ("mmr", {"search_type": "mmr",
             "search_kwargs": {"k": RETRIEVAL_K, "fetch_k": RETRIEVAL_FETCH_K, "lambda_mult": MMR_LAMBDA}}),
])
def test_retrieve_node_uses_config_settings(monkeypatch, search_type, expected):
    calls = []
    monkeypatch.setattr(nodes, "RETRIEVAL_SEARCH_TYPE", search_type)

    class FakeStore:
        def as_retriever(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(invoke=lambda text: [])

    monkeypatch.setattr(nodes, "get_vectorstore", lambda: FakeStore())

    nodes.retrieve_node({"question": SimpleNamespace(id="Q1", text="q")})

    assert calls == [expected]


def test_default_retriever_is_similarity_and_unknown_type_is_rejected(monkeypatch):
    from app.config import RETRIEVAL_SEARCH_TYPE
    assert RETRIEVAL_SEARCH_TYPE == "similarity"
    monkeypatch.setattr(nodes, "RETRIEVAL_SEARCH_TYPE", "hybrid")
    with pytest.raises(ValueError, match="RETRIEVAL_SEARCH_TYPE"):
        nodes.retriever_settings()


def test_hallucination_judge_reasons_before_verdict():
    assert list(HallucinationEvaluation.model_fields)[0] == "reasoning"


def test_analyst_draft_writes_answer_before_deciding_answer_found():
    assert list(AnalystDraft.model_fields) == ["answer_text", "answer_found"]
    assert AnalystDraft.model_fields["answer_found"].is_required()


def test_draft_node_builds_answer_from_question(monkeypatch):
    class FakeLLM:
        def with_structured_output(self, schema):
            assert schema is AnalystDraft
            return SimpleNamespace(invoke=lambda prompt: AnalystDraft(answer_text="a", answer_found=True))
    monkeypatch.setattr(nodes, "_llm", lambda state: FakeLLM())
    question = Question(id="[RFP] A1", text="q", category="Tech", sheet="RFP", row_index=4)

    result = nodes.draft_node({"question": question, "analyst": company_analysts["Tech"],
                               "context_text": "c", "feedback": "", "attempt": 0})

    draft = result["draft"]
    assert (draft.question_id, draft.question_text, draft.assigned_analyst, draft.answer_text) ==         ("[RFP] A1", "q", company_analysts["Tech"].name, "a")
    assert (draft.category, draft.sheet, draft.row_index) == ("Tech", "RFP", 4)
    assert draft.sources_used == [] and result["attempt"] == 1


def _draft_with(monkeypatch, text, found):
    monkeypatch.setattr(nodes, "_llm", lambda state: SimpleNamespace(with_structured_output=lambda schema: SimpleNamespace(
        invoke=lambda prompt: AnalystDraft(answer_text=text, answer_found=found))))
    question = Question(id="[RFP] A1", text="Are you PCI DSS certified?", category="Security", sheet="RFP", row_index=0)
    return nodes.draft_node({"question": question, "analyst": company_analysts["Security"],
                             "context_text": "c", "feedback": "", "attempt": 0})["draft"]


def test_answer_found_false_overrides_paraphrased_refusal_and_keeps_it_in_review_note(monkeypatch):
    paraphrase = "PCI DSS is not mentioned in the available information. [**Source: a.pdf (Page 1)**]"
    draft = _draft_with(monkeypatch, paraphrase, False)
    assert draft.answer_text == FAIL_MSG
    assert draft.review_note == f"Model text before not-found override: {paraphrase}"
    assert nodes.route_after_draft({"draft": draft}) == "conflict_audit"
    answer = nodes.finalize_node({"draft": draft, "conflicts": "", "status_map": {}, "allowed_sources": []})["answer"]
    assert (answer.status, answer.sources_used) == (Status.not_found, [])
    assert answer.review_note == draft.review_note


def test_answer_found_false_with_plain_fail_message_adds_no_note(monkeypatch):
    draft = _draft_with(monkeypatch, FAIL_MSG_PREFIX + ".", False)
    assert (draft.answer_text, draft.review_note) == (FAIL_MSG, "")


def test_answer_found_true_keeps_partial_answer(monkeypatch):
    partial = "SSO via SAML 2.0 [**Source: a.pdf (Page 1)**]. SCIM is not mentioned."
    draft = _draft_with(monkeypatch, partial, True)
    assert (draft.answer_text, draft.review_note) == (partial, "")


def test_exact_fail_message_with_answer_found_true_still_routes_as_not_found(monkeypatch):
    draft = _draft_with(monkeypatch, FAIL_MSG, True)  # text check is the fallback
    assert nodes.route_after_draft({"draft": draft}) == "conflict_audit"


@pytest.mark.parametrize("text", [
    "SCIM provisioning is not mentioned in the provided context.",
    "Service credits are not explicitly stated.",
    "The context does not specify the lockout threshold.",
    "There is no mention of cyber insurance.",
    "Whether reports are shared is not provided in the documentation.",
    "We are unable to confirm this.",
])
def test_absence_statements_are_detected(text):
    assert nodes.has_absence_statement(text)


@pytest.mark.parametrize("text", [
    "LogistiComp WMS is not available on-premises.",
    "No customer data is used to train AI models.",
    "Keys are rotated annually [**Source: Not mentioned policy.pdf (Page 1)**].",  # citations ignored
    "Yes, MFA is mandatory for all employees.",
])
def test_facts_and_citations_are_not_absence_statements(text):
    assert not nodes.has_absence_statement(text)


def _finalize(text, review_note=""):
    d = Answer(question_id="Q1", question_text="q", assigned_analyst="a", answer_text=text, review_note=review_note)
    return nodes.finalize_node({"draft": d, "conflicts": "", "status_map": {}, "allowed_sources": []})["answer"]


def test_finalize_flags_absence_statement_for_review():
    answer = _finalize("PCI DSS is not mentioned in the available information.")
    assert (answer.status, answer.review_note) == (Status.needs_review, nodes.ABSENCE_NOTE)


def test_finalize_keeps_give_up_note_and_adds_absence_note():
    answer = _finalize("Retention is not specified.", review_note="Judge: unsupported")
    assert (answer.status, answer.review_note) == (Status.needs_review, f"Judge: unsupported\n{nodes.ABSENCE_NOTE}")


def test_finalize_fail_message_stays_not_found_and_partial_gets_only_partial_note():
    assert (_finalize(FAIL_MSG).status, _finalize(FAIL_MSG).review_note) == (Status.not_found, "")
    partial = _finalize(f"SSO yes. SCIM is not mentioned. {FAIL_MSG}")
    assert (partial.status, partial.review_note) == (Status.needs_review, nodes.PARTIAL_NOTE)


def test_finalize_plain_answer_stays_answered():
    assert _finalize("Yes, MFA is mandatory for all employees.").status == Status.answered
