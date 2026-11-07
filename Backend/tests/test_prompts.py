"""Builders and LLM-facing schemas vs tests/prompt_snapshots/ (byte-exact, no LLM).
After an intended prompt or schema change, regenerate and review the diff: cd Backend; ..\\venv\\Scripts\\python -m tests.test_prompts
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent.prompts import (
    analyst_draft_prompt, citation_feedback, conflict_audit_prompt, evaluation_judge_prompt, hallucination_judge_prompt,
    pdf_extraction_prompt, persona_rules, status_classifier_prompt,
)
from app.agent.schemas import (
    AnalystDraft, ConflictDetection, HallucinationEvaluation, RFPQuestions, StatusChoices, company_analysts,
)
from app.config import FAIL_MSG, FAIL_MSG_PREFIX
from app.evaluation import EvaluationResult

SNAPSHOT_DIR = Path(__file__).parent / "prompt_snapshots"

# Greek, braces and trailing spaces on purpose: must pass through untouched.
QUESTION = "Is data encrypted at rest? {braces} Κρυπτογράφηση; "
CONTEXT = (
    "--- SOURCE: policy.pdf (Page 1) ---\nAES-256 at rest. {x} \n\n"
    "--- SOURCE: past.xlsx - Sheet1 (Row 7) ---\nQ: Κρυπτογράφηση;\nA: Yes\n\n"
    "--- SOURCE: past.xlsx (Row 9) ---\nKeys rotate yearly."
)
ANSWER = "Yes, AES-256. [**Source: policy.pdf (Page 1)**] "
EXPECTED = "Yes, AES-256 at rest. "
FEEDBACK = "Remove the claim about FIPS. "
RFP_TEXT = "Page one text \nPage two"
SPECS = [
    SimpleNamespace(column="Supported (Yes/No)", allowed_values=["Yes", "No"]),
    SimpleNamespace(column="Κατάσταση", allowed_values=["Applicable", "Not Applicable", "Don't know"]),
]


def _persona(category):
    analyst = company_analysts[category]
    return persona_rules(analyst.name, analyst.role_description, analyst.tone)


# Every model passed to with_structured_output: field order, descriptions and docstrings reach the LLM.
LLM_SCHEMAS = [RFPQuestions, AnalystDraft, HallucinationEvaluation, ConflictDetection, StatusChoices, EvaluationResult]


def _schema(model):
    return json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False) + "\n"


def render_all():
    return {
        "persona_security": _persona("Security"),
        "persona_tech": _persona("Tech"),
        "persona_product": _persona("Product"),
        "draft_security": analyst_draft_prompt(_persona("Security"), QUESTION, CONTEXT),
        "draft_security_feedback": analyst_draft_prompt(_persona("Security"), QUESTION, CONTEXT, FEEDBACK, ANSWER),
        "citation_feedback": citation_feedback(["other.pdf (Page 3)", "past.xlsx (Row 8)"], ["policy.pdf (Page 1)", "past.xlsx - Sheet1 (Row 7)"]),
        "citation_feedback_none": citation_feedback([], ["policy.pdf (Page 1)"]),
        "hallucination_judge": hallucination_judge_prompt(QUESTION, CONTEXT, ANSWER),
        "conflict_audit": conflict_audit_prompt(QUESTION, CONTEXT),
        "status_classifier": status_classifier_prompt(QUESTION, ANSWER, SPECS),
        "pdf_extraction": pdf_extraction_prompt(RFP_TEXT),
        "evaluation_judge": evaluation_judge_prompt(QUESTION, ANSWER, EXPECTED),
        **{f"schema_{model.__name__}": _schema(model) for model in LLM_SCHEMAS},
    }


@pytest.mark.parametrize("name", render_all())
def test_prompt_matches_snapshot(name):
    # Bytes, not read_text: no newline translation.
    assert render_all()[name] == (SNAPSHOT_DIR / f"{name}.txt").read_bytes().decode("utf-8")


def test_no_orphan_snapshots():
    assert {p.stem for p in SNAPSHOT_DIR.glob("*.txt")} == set(render_all())


def test_snapshots_end_lines_with_lf_only():
    for path in SNAPSHOT_DIR.glob("*.txt"):
        assert b"\r" not in path.read_bytes(), path.name


def test_persona_includes_analyst_and_fail_message():
    persona = persona_rules("NAME", "ROLE", "TONE")
    assert all(text in persona for text in ("NAME", "ROLE", "TONE", FAIL_MSG))


def test_draft_has_feedback_suffix_only_with_feedback():
    marker = "[URGENT FEEDBACK FROM JUDGE - FIX THIS]"
    assert marker not in analyst_draft_prompt("P", QUESTION, CONTEXT)
    with_feedback = analyst_draft_prompt("P", QUESTION, CONTEXT, FEEDBACK, ANSWER)
    assert marker in with_feedback and FEEDBACK in with_feedback and ANSWER in with_feedback


def test_draft_includes_inputs():
    prompt = analyst_draft_prompt("PERSONA", QUESTION, CONTEXT)
    assert prompt.startswith("PERSONA\n") and QUESTION in prompt and CONTEXT in prompt


def test_judge_and_audit_include_inputs():
    judge = hallucination_judge_prompt(QUESTION, CONTEXT, ANSWER)
    assert QUESTION in judge and CONTEXT in judge and ANSWER in judge
    audit = conflict_audit_prompt(QUESTION, CONTEXT)
    assert QUESTION in audit and CONTEXT in audit


def test_judge_has_past_rfp_rule():
    judge = hallucination_judge_prompt(QUESTION, CONTEXT, ANSWER)
    assert "PAST RFP ROWS:" in judge and "‘No’ contradicts it" in judge


def test_classifier_lists_every_column_and_value():
    prompt = status_classifier_prompt(QUESTION, ANSWER, SPECS)
    assert QUESTION in prompt and ANSWER in prompt
    for spec in SPECS:
        assert f'COLUMN: "{spec.column}"' in prompt
        assert all(f'    - "{value}"' in prompt for value in spec.allowed_values)


def test_pdf_extraction_ends_with_rfp_text():
    assert pdf_extraction_prompt(RFP_TEXT).endswith(f"RFP TEXT:\n{RFP_TEXT}")


def test_evaluation_judge_includes_inputs_and_fail_prefix():
    prompt = evaluation_judge_prompt(QUESTION, ANSWER, EXPECTED)
    assert all(text in prompt for text in (QUESTION, ANSWER, EXPECTED, FAIL_MSG_PREFIX))


if __name__ == "__main__":
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    for old in SNAPSHOT_DIR.glob("*.txt"):
        old.unlink()
    for name, text in render_all().items():
        (SNAPSHOT_DIR / f"{name}.txt").write_bytes(text.encode("utf-8"))
    print(f"Wrote {len(render_all())} snapshots to {SNAPSHOT_DIR}. Review with: git diff -- {SNAPSHOT_DIR}")
