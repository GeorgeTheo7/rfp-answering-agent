from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_community.callbacks.manager import get_openai_callback

from app.agent.nodes import calculate_cost, _canonical_value
from app.agent.prompts import evaluation_judge_prompt

# ==========================================
# 6. LLM JUDGE (ACCURACY EVALUATOR)
# ==========================================
class EvaluationResult(BaseModel):
    score: int = Field(description="Score from 0 to 100 representing accuracy.")
    reasoning: str = Field(description="Brief explanation of the score.")

def run_llm_judge(question: str, generated_answer: str, expected_answer: str, model_name: str = "gpt-4o-mini"):
    llm = ChatOpenAI(model=model_name, temperature=0, max_retries=5, timeout=60)
    structured_llm = llm.with_structured_output(EvaluationResult)
    
    prompt = evaluation_judge_prompt(question, generated_answer, expected_answer)
    try:
        with get_openai_callback() as cb:
            result = structured_llm.invoke(prompt)
            eval_cost = calculate_cost(model_name, cb)
                
        return result, eval_cost
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
