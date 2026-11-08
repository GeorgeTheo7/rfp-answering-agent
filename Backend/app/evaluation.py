import re
from typing import Literal, Optional

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_community.callbacks.manager import get_openai_callback

from app.agent.nodes import calculate_cost, _canonical_value
from app.agent.prompts import evaluation_judge_prompt
from app.config import JUDGE_MODEL

# ==========================================
# 6. LLM JUDGE (ACCURACY EVALUATOR)
# ==========================================
class EvaluationResult(BaseModel):
    score: int = Field(description="Score from 0 to 100 representing accuracy.")
    reasoning: str = Field(description="Brief explanation of the score.")

# LLM-facing judge output; field order = writing order (reasoning before verdict and score).
# A comment, not a docstring: a docstring would become the schema description the model sees.
class JudgeOutput(BaseModel):
    reasoning: str = Field(description="Brief explanation, written before the verdict and the score.")
    generated_verdict: Literal["yes", "no", "neither"] = Field(
        description="Does the Generated Answer, on its own, mean yes, no, or neither? Judge the meaning, not the wording.")
    score: int = Field(description="Score from 0 to 100: how well the Generated Answer covers the facts in the Expected Answer.")

VERDICT_CAP = 20
_LEADING_YES_NO = re.compile(r"^\W*(yes|no)\b", re.IGNORECASE)

def expected_verdict(expected_answer: str) -> Optional[str]:
    """"yes"/"no" if the expected answer starts with the word Yes or No (any case), else None."""
    match = _LEADING_YES_NO.match(expected_answer or "")
    return match.group(1).lower() if match else None

def apply_verdict_cap(output: JudgeOutput, expected_answer: str) -> EvaluationResult:
    """Score capped at VERDICT_CAP when the verdicts are opposite (yes vs no). "neither" never caps."""
    expected = expected_verdict(expected_answer)
    score, reasoning = output.score, output.reasoning
    opposite = expected and output.generated_verdict in ("yes", "no") and output.generated_verdict != expected
    if opposite and score > VERDICT_CAP:
        score = VERDICT_CAP
        reasoning += f" [Capped at {VERDICT_CAP}: expected '{expected}', generated '{output.generated_verdict}'.]"
    return EvaluationResult(score=score, reasoning=reasoning)

def run_llm_judge(question: str, generated_answer: str, expected_answer: str):
    """Always JUDGE_MODEL, never the agent's model."""
    llm = ChatOpenAI(model=JUDGE_MODEL, temperature=0, max_retries=5, timeout=60)
    structured_llm = llm.with_structured_output(JudgeOutput)

    prompt = evaluation_judge_prompt(question, generated_answer, expected_answer)
    try:
        with get_openai_callback() as cb:
            output = structured_llm.invoke(prompt)
            eval_cost = calculate_cost(JUDGE_MODEL, cb)
        return apply_verdict_cap(output, expected_answer), eval_cost
    except Exception as e:
        return EvaluationResult(score=0, reasoning=f"Error evaluating: {str(e)}"), 0.0

def categorical_eval(generated_value: str, expected_value: str, allowed_values: list) -> "EvaluationResult":
    """Deterministic evaluation for constrained / list-value answers
    (e.g. Applicable/Not Applicable, Yes/No). Compares the ALREADY classified value
    of the generated answer with the ground-truth value. Score 100 if they match, else 0."""
    gen = _canonical_value(generated_value, allowed_values) or (generated_value or "").strip()
    exp = _canonical_value(expected_value, allowed_values) or (expected_value or "").strip()
    if gen and exp and gen.strip().lower() == exp.strip().lower():
        return EvaluationResult(score=100, reasoning=f"Categorical match: generated '{gen}' == expected '{exp}'.")
    return EvaluationResult(score=0, reasoning=f"Categorical mismatch: generated '{gen or 'N/A'}' vs expected '{exp}'.")
