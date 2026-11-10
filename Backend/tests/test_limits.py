from types import SimpleNamespace

import openpyxl
import pymupdf
import pytest
from fastapi.testclient import TestClient

from app import api, config
from app.agent.schemas import Answer
from app.config import DEFAULT_AGENT_MODEL, MODEL_SETTINGS
from app.main import app

ANSWERS = [Answer(question_id="Q1", question_text="q", assigned_analyst="CISO", answer_text="Yes",
                  sources_used=[], category="Security", cost=0.0)]


def _fail_graph(*args, **kwargs):
    raise AssertionError("the graph must not run")


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(config, "DEMO_MODE", True)
    return monkeypatch


def _pdf(tmp_path, pages):
    doc = pymupdf.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 72), f"Question {i + 1}?")
    path = tmp_path / "rfp.pdf"
    doc.save(str(path))
    doc.close()
    return path


def _xlsx(tmp_path, n, expected=False):
    wb = openpyxl.Workbook()
    wb.active.append(["ID", "Question"] + (["Expected Answer"] if expected else []))
    for i in range(n):
        wb.active.append([f"Q{i}", f"Do you do thing {i}?"] + (["Yes"] if expected else []))
    path = tmp_path / "rfp.xlsx"
    wb.save(path)
    return path


def _post(endpoint, path, model=None):
    data = {"model": model} if model else {}
    with open(path, "rb") as f:
        return TestClient(app).post(f"/api/rfp/{endpoint}", files={"file": (path.name, f)}, data=data)


def test_env_int_uses_default_when_unset_or_empty(monkeypatch):
    monkeypatch.delenv("MAX_QUESTIONS", raising=False)
    assert config._env_int("MAX_QUESTIONS", 55) == 55
    monkeypatch.setenv("MAX_QUESTIONS", "  ")
    assert config._env_int("MAX_QUESTIONS", 55) == 55
    monkeypatch.setenv("MAX_QUESTIONS", "7")
    assert config._env_int("MAX_QUESTIONS", 55) == 7


def test_config_reports_limits_and_allowed_models(monkeypatch):
    monkeypatch.setattr(config, "DEMO_MODE", False)
    body = TestClient(app).get("/api/config").json()
    assert body == {"demo_mode": False, "max_upload_mb": config.MAX_UPLOAD_MB, "max_pdf_pages": config.MAX_PDF_PAGES,
                    "max_questions": config.MAX_QUESTIONS, "allowed_models": list(MODEL_SETTINGS)}

    monkeypatch.setattr(config, "DEMO_MODE", True)
    monkeypatch.setattr(config, "DEMO_MODELS", (DEFAULT_AGENT_MODEL, "not-a-model"))
    assert TestClient(app).get("/api/config").json()["allowed_models"] == [DEFAULT_AGENT_MODEL]


def test_unknown_model_is_rejected_even_without_demo_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(config, "DEMO_MODE", False)
    monkeypatch.setattr(api, "rfp_graph", SimpleNamespace(invoke=_fail_graph))
    for endpoint, path in (("analyze", _pdf(tmp_path, 1)), ("evaluate", _xlsx(tmp_path, 1, expected=True))):
        response = _post(endpoint, path, model="gpt-9-ultra")
        assert response.status_code == 400
        assert response.json()["detail"] == "Model 'gpt-9-ultra' is not available."


def test_demo_mode_only_allows_demo_models(tmp_path, demo):
    demo.setattr(api, "rfp_graph", SimpleNamespace(invoke=_fail_graph))
    response = _post("analyze", _pdf(tmp_path, 1), model="gpt-5-mini")
    assert response.status_code == 400 and "not available" in response.json()["detail"]


def test_demo_mode_rejects_large_files_before_the_graph(tmp_path, demo):
    demo.setattr(config, "MAX_UPLOAD_MB", 0)
    demo.setattr(api, "rfp_graph", SimpleNamespace(invoke=_fail_graph))
    response = _post("evaluate", _xlsx(tmp_path, 1, expected=True))
    assert response.status_code == 400
    assert response.json()["detail"] == "The file is larger than 0 MB (public demo limit)."


def test_demo_mode_rejects_long_pdfs_before_the_graph(tmp_path, demo):
    demo.setattr(config, "MAX_PDF_PAGES", 2)
    demo.setattr(api, "rfp_graph", SimpleNamespace(invoke=_fail_graph))
    response = _post("analyze", _pdf(tmp_path, 3))
    assert response.status_code == 400
    assert response.json()["detail"] == "The PDF has 3 pages; the public demo allows up to 2."


def test_limits_are_off_without_demo_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(config, "DEMO_MODE", False)
    monkeypatch.setattr(config, "MAX_PDF_PAGES", 2)
    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 0)
    monkeypatch.setattr(api, "rfp_graph", SimpleNamespace(invoke=lambda *a, **k: {"final_answers": ANSWERS}))
    assert _post("analyze", _pdf(tmp_path, 3)).status_code == 200


def test_demo_mode_rejects_too_many_questions_before_answering(tmp_path, demo):
    # Real graph: Excel extraction needs no LLM, and the limit stops the run before any question is answered.
    demo.setattr(config, "MAX_QUESTIONS", 2)
    response = _post("analyze", _xlsx(tmp_path, 3))
    assert response.status_code == 400
    assert response.json()["detail"] == "The file has 3 questions; the public demo allows up to 2."


def test_question_limit_allows_files_at_the_limit(tmp_path, demo):
    from app.agent.nodes import extract_questions_node
    demo.setattr(config, "MAX_QUESTIONS", 3)
    state = {"rfp_input_path": str(_xlsx(tmp_path, 3)), "selected_model": DEFAULT_AGENT_MODEL}
    assert len(extract_questions_node(state)["extracted_questions"]) == 3
