from types import SimpleNamespace

import pytest

from app.agent import nodes
from app.agent.schemas import ExtractedQuestion, Question, RFPQuestions, StatusChoices, StatusSpec
from app.config import MODEL_PRICING, MODEL_SETTINGS


@pytest.fixture
def clients(monkeypatch):
    """Records the kwargs of every ChatOpenAI client; each returns `result` from structured output."""
    made = []

    def fake_chat(**kwargs):
        made.append(kwargs)
        return SimpleNamespace(with_structured_output=lambda schema: SimpleNamespace(invoke=lambda prompt: fake_chat.result))

    monkeypatch.setattr(nodes, "ChatOpenAI", fake_chat)
    fake_chat.made = made
    return fake_chat


def test_luna_uses_low_effort_without_temperature_and_others_keep_temperature_0(clients):
    nodes.chat_model("gpt-6-luna", timeout=90)
    nodes.chat_model("gpt-4o-mini", timeout=90)
    nodes.chat_model("gpt-5-mini", timeout=90)
    luna, mini, five = clients.made
    assert luna["reasoning_effort"] == "low" and "temperature" not in luna
    assert mini["temperature"] == 0 and "reasoning_effort" not in mini
    assert five["temperature"] == 0


def test_unknown_model_is_rejected():
    with pytest.raises(ValueError, match="MODEL_SETTINGS"):
        nodes.chat_model("gpt-nope", timeout=60)


def test_every_configured_model_is_priced():
    assert set(MODEL_SETTINGS) <= set(MODEL_PRICING)


def test_question_subgraph_llm_uses_the_selected_model_settings(clients):
    # _llm builds the client for draft, hallucination judge and conflict audit.
    nodes._llm({"selected_model": "gpt-6-luna"})
    assert clients.made[-1] == {"model": "gpt-6-luna", "max_retries": 5, "timeout": 90, "reasoning_effort": "low"}


def test_classifier_uses_the_selected_model_settings(clients):
    clients.result = StatusChoices(choices=[])
    question = Question(id="[S] 1", text="q", category="Tech")
    nodes.classify_statuses(question, "a", [StatusSpec(column="Yes/No", allowed_values=["Yes", "No"])], "gpt-6-luna")
    assert clients.made[-1]["model"] == "gpt-6-luna" and clients.made[-1]["reasoning_effort"] == "low"


def test_pdf_extraction_uses_the_selected_model_settings(clients, monkeypatch):
    clients.result = RFPQuestions(questions=[ExtractedQuestion(id="Q1", text="q", category="Tech")])
    monkeypatch.setattr(nodes, "PyMuPDFLoader", lambda path: SimpleNamespace(load=lambda: []))
    nodes.extract_questions_node({"rfp_input_path": "rfp.pdf", "selected_model": "gpt-6-luna"})
    assert clients.made[-1]["model"] == "gpt-6-luna" and "temperature" not in clients.made[-1]
