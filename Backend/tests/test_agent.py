from types import SimpleNamespace

from app.agent import nodes
from app.agent.nodes import _canonical_value
from app.agent.schemas import AnalystDraft, HallucinationEvaluation, Question, company_analysts
from app.config import MMR_LAMBDA, RETRIEVAL_FETCH_K, RETRIEVAL_K

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


def test_retrieve_node_uses_config_settings(monkeypatch):
    calls = []

    class FakeStore:
        def as_retriever(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(invoke=lambda text: [])

    monkeypatch.setattr(nodes, "get_vectorstore", lambda: FakeStore())

    nodes.retrieve_node({"question": SimpleNamespace(id="Q1", text="q")})

    assert calls == [{
        "search_type": "mmr",
        "search_kwargs": {"k": RETRIEVAL_K, "fetch_k": RETRIEVAL_FETCH_K, "lambda_mult": MMR_LAMBDA},
    }]


def test_hallucination_judge_reasons_before_verdict():
    assert list(HallucinationEvaluation.model_fields)[0] == "reasoning"


def test_analyst_draft_has_only_answer_text():
    assert list(AnalystDraft.model_fields) == ["answer_text"]


def test_draft_node_builds_answer_from_question(monkeypatch):
    class FakeLLM:
        def with_structured_output(self, schema):
            assert schema is AnalystDraft
            return SimpleNamespace(invoke=lambda prompt: AnalystDraft(answer_text="a"))
    monkeypatch.setattr(nodes, "_llm", lambda state: FakeLLM())
    question = Question(id="[RFP] A1", text="q", category="Tech", sheet="RFP", row_index=4)

    result = nodes.draft_node({"question": question, "analyst": company_analysts["Tech"],
                               "context_text": "c", "feedback": "", "attempt": 0})

    draft = result["draft"]
    assert (draft.question_id, draft.question_text, draft.assigned_analyst, draft.answer_text) ==         ("[RFP] A1", "q", company_analysts["Tech"].name, "a")
    assert (draft.category, draft.sheet, draft.row_index) == ("Tech", "RFP", 4)
    assert draft.sources_used == [] and result["attempt"] == 1
