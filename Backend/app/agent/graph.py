from langgraph.graph import StateGraph, START, END
from langchain_community.callbacks.manager import get_openai_callback

from app.config import DEFAULT_AGENT_MODEL
from app.agent.schemas import Answer, QuestionAnsweringState, QuestionState, RFPGraphState, Status, company_analysts
from app.agent.nodes import (
    extract_questions_node, route_questions, generate_final_report_node, calculate_cost,
    retrieve_node, draft_node, judge_node, give_up_node, conflict_audit_node, classify_status_node, finalize_node,
    route_after_draft, route_after_judge, route_after_validation, validate_citations_node,
)

# ==========================================
# QUESTION SUBGRAPH (one question)
# ==========================================
question_workflow = StateGraph(QuestionState)
question_workflow.add_node("retrieve", retrieve_node)
question_workflow.add_node("draft", draft_node)
question_workflow.add_node("validate_citations", validate_citations_node)
question_workflow.add_node("judge", judge_node)
question_workflow.add_node("give_up", give_up_node)
question_workflow.add_node("conflict_audit", conflict_audit_node)
question_workflow.add_node("classify_status", classify_status_node)
question_workflow.add_node("finalize", finalize_node)
question_workflow.add_edge(START, "retrieve")
question_workflow.add_edge("retrieve", "draft")
question_workflow.add_conditional_edges("draft", route_after_draft, ["validate_citations", "conflict_audit"])
question_workflow.add_conditional_edges("validate_citations", route_after_validation, ["judge", "draft", "give_up"])
question_workflow.add_conditional_edges("judge", route_after_judge, ["draft", "give_up", "conflict_audit"])
question_workflow.add_edge("give_up", "conflict_audit")
question_workflow.add_edge("conflict_audit", "classify_status")
question_workflow.add_edge("classify_status", "finalize")
question_workflow.add_edge("finalize", END)
question_graph = question_workflow.compile()

def answer_question_node(state: QuestionAnsweringState):
    """LangGraph node wrapper. Isolates failures per question so that a single
    error (rate limit, timeout, schema validation, etc.) does NOT bring down the whole
    batch. On success, the behaviour is identical to before."""
    question = state["question"]
    chosen_model = state.get("selected_model", DEFAULT_AGENT_MODEL)
    analyst = company_analysts.get(question.category, company_analysts["Product"])

    try:
        # One callback around the whole subgraph captures every LLM call of this question.
        with get_openai_callback() as cb:
            result = question_graph.invoke({"question": question, "selected_model": chosen_model, "analyst": analyst})
            total_cost = calculate_cost(chosen_model, cb)
        final_answer = result["answer"]
        final_answer.cost = total_cost
        return {"completed_answers": [final_answer]}
    except Exception as e:
        error_detail = f"{type(e).__name__}: {str(e)}"
        print(f"   [✗] FATAL error on {question.id} -> {error_detail}")
        # Distinct error message — NOT the "couldn't find answer" one.
        fallback = Answer(
            question_id=question.id,
            question_text=question.text,
            assigned_analyst=analyst.name,
            answer_text=(
                "⚠️ SYSTEM ERROR: This question could not be processed automatically "
                f"due to a technical issue ({error_detail}). "
                "Note: this is NOT a 'missing answer' — the knowledge base may well "
                "contain the answer. Please re-run this question or review it manually."
            ),
            sources_used=[],
            conflicts="",
            cost=0.0,
            category=question.category,
            sheet=question.sheet,
            row_index=question.row_index,
            status=Status.error,
        )
        return {"completed_answers": [fallback]}

# ==========================================
# RFP GRAPH
# ==========================================
workflow = StateGraph(RFPGraphState)
workflow.add_node("extract_node", extract_questions_node)
workflow.add_node("answer_node", answer_question_node)
workflow.add_node("report_node", generate_final_report_node)
workflow.add_edge(START, "extract_node")
workflow.add_conditional_edges("extract_node", route_questions, ["answer_node"])
workflow.add_edge("answer_node", "report_node")
workflow.add_edge("report_node", END)
rfp_graph = workflow.compile()
