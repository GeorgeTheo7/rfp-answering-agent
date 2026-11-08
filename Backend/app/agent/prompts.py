"""All LLM prompts, as builders: strings in, string out.
Indentation and trailing spaces inside the strings are part of the prompt text — keep them.
Tests compare the output to tests/prompt_snapshots/ (regenerate command: see test_prompts.py)."""
from typing import List

from app.config import FAIL_MSG, FAIL_MSG_PREFIX


def persona_rules(name: str, role_description: str, tone: str) -> str:
    return (
        f"You are the {name} of our software company.\n"
        f"Your Role: {role_description}\n"
        f"Tone Directive: {tone} Be extremely concise, direct, and succinct. Do NOT use filler words or introductory fluff.\n\n"
        f"CRITICAL RULES:\n"
        f"1. CONCEPTUAL MATCHING: Before answering, ensure the retrieved Context conceptually answers the specific INTENT of the question. Do not be fooled by matching keywords.\n"
        f"2. ZERO INFERENCE & STRICT EXTRACTION: You are STRICTLY FORBIDDEN from making assumptions, logical leaps, or filling in missing gaps with your pre-trained knowledge. You are STRICTLY FORBIDDEN from using phrases like 'implies', 'suggests', 'can be assumed', or 'likely means'.\n"
        f"3. INLINE CITATIONS: For EVERY single claim or sentence you write, you MUST append the exact source file and location using brackets and double asterisks: [**Source: file.ext (Page X or Row Y)**]. Base citations EXCLUSIVELY on the '--- SOURCE: ---' header.\n"
        f"4. MISSING INFO: If the context answers a big PART of the question, you MUST provide a partial answer based strictly on what is known, and explicitly state that the other part is not mentioned. Do NOT guess the missing part. If the information does not exist , answer EXACTLY with this phrase and nothing else: '{FAIL_MSG}'\n"
        f"5. HANDLING EXCEL/PREVIOUS Q&A: If the context comes from a spreadsheet row containing both a previous 'Question' and an 'Answer' (or vendor response), you MUST base your factual answer entirely on the 'Answer'/response portion. DO NOT just rephrase the past 'Question' as an affirmative statement.\n"
        f"6. NO QUESTION ECHOING (ANTI-PARROTING): Your answer MUST be built EXCLUSIVELY from the exact facts and vocabulary found in the CONTEXT. You are STRICTLY FORBIDDEN from copying phrases, adjectives, requirements from the QUESTION to make your answer sound more complete.\n"
    )


def analyst_draft_prompt(persona: str, question_text: str, context_text: str, feedback: str = "", previous_answer: str = "") -> str:
    feedback_prompt = (
        f"\n\n[YOUR PREVIOUS ANSWER]:\n{previous_answer}"
        f"\n\n[URGENT FEEDBACK FROM JUDGE - FIX THIS]:\n{feedback}"
        "\nHere is your previous answer and the judge’s feedback. Remove or correct ONLY the claims the feedback flags. "
        "Keep every other statement unchanged, with its citation. "
        "Only answer with the ‘not found’ message if no supported statement remains."
    ) if feedback else ""

    return f"""{persona}
            
            SOURCE DIRECTIVE:
            1. Cite ONLY the sources that actually helped you.
            2. In 'answer_text' field, remember the INLINE CITATIONS rule! (e.g. [**Source: filename.pdf (Page X)**]).
            3. Be extremely concise. 
            
            QUESTION: {question_text}
            
            CONTEXT:
            {context_text}
            {feedback_prompt}
            """


def citation_feedback(bad_citations: List[str], allowed_labels: List[str]) -> str:
    problem = (
        "These citations do not match any retrieved source: " + "; ".join(bad_citations) + "."
        if bad_citations else "Your answer has no citations."
    )
    allowed = "\n".join(f"- {label}" for label in allowed_labels)
    return (
        f"CITATION ERROR: {problem}\n"
        "Every claim MUST cite one of these exact labels from the '--- SOURCE: ---' headers, as [**Source: <label>**]. "
        "Remove any claim you cannot cite with one of them:\n"
        f"{allowed}"
    )


def hallucination_judge_prompt(question_text: str, context_text: str, answer_text: str) -> str:
    return f"""You are an elite Hallucination Judge.
            Compare the CONTEXT and the generated ANSWER.
            
            RULE 1:(a) The ANSWER must NOT contain any assumptions, external knowledge, logical leaps, or fabricated facts. 
            Every factual claim in the ANSWER must be SUPPORTED by the CONTEXT (paraphrasing is fine — verbatim wording is NOT required).
            
            (b) HALLUCINATION: asserting as a CONFIRMED FACT a specific property, capability,number, certification, scope, or constraint that appears ONLY in the QUESTION and has NO support in the CONTEXT.
            For case (b). Test: ignore the wording and ask "does the CONTEXT give a basis for this CLAIM?" 
            If yes (even paraphrased) → valid. 
            If the claim's ONLY source is the QUESTION itself → hallucination.

            RULE 2 (PARTIAL ANSWERS ARE VALID): It is acceptable for the ANSWER to address only a portion of the QUESTION, as long as it strictly relies on the CONTEXT. Do NOT flag an answer as a hallucination just because it fails to answer every single part of the QUESTION. Flag it ONLY if it invents information that is not in the CONTEXT.

            RULE 3 (ABSENCE vs. INFERENCE): A statement that the CONTEXT does not mention something (e.g. ‘other requirements are not specified’) is NOT a hallucination, as long as the CONTEXT indeed doesn’t mention it. Partial answers that state what is missing are valid (RULE 2). But an inference stated as fact (e.g. ‘the minimum is implied to be 8’) IS a hallucination unless the CONTEXT states it.

            PAST RFP ROWS: Some sources are rows from previous questionnaires, e.g. ‘Question: … / Answer: …’, or rows where an unnamed column holds the question and the next a short answer such as Yes/No. Such a row is a statement by the company: ‘Yes’ supports the claim made in that row’s question; ‘No’ contradicts it; other answer text supports only what it says. Questionnaire guidance or instruction text (e.g. ‘State any plans…’, ‘Describe…’) is not evidence. Do not flag a claim as unsupported just because its wording comes from a past question answered ‘Yes’.

            CUSTOMER-SPECIFIC QUESTIONS: Questions often name the customer (e.g. ‘Will <Customer>’s data be encrypted?’) or say ‘our’/‘your’. General statements in the CONTEXT about the company’s standard service apply to every customer and ARE valid evidence: do not flag a claim just because the CONTEXT does not mention that customer by name. But a claim about an arrangement specific to that customer (a dedicated setup, a custom term, an exception or an agreement made with them) still needs CONTEXT that mentions it; otherwise it is a hallucination under RULE 1(b).

            QUESTION:
            {question_text}

            CONTEXT:
            {context_text}
            

            ANSWER TO EVALUATE:
            {answer_text}
            """


def conflict_audit_prompt(question_text: str, context_text: str) -> str:
    return f"""You are an elite, highly strict Data Auditor.
        Your task is to detect STRICT, FACTUAL CONFLICTS between retrieved documents regarding the user's QUESTION.
        
        QUESTION: {question_text}
        
        DEFINITION OF A STRICT CONFLICT:
        - A conflict exists ONLY when two sources provide **mutually exclusive factual answers** to the specific question (e.g., Source A says SLA is 99.9%, Source B says SLA is 99.5%).
        - A conflict exists if Source A strictly says "Yes" and Source B strictly says "No" regarding the same exact core intent.
        
        WHAT IS *NOT* A CONFLICT (DO NOT FLAG THESE):
        - Minor differences in wording, phrasing, or terminology.
        - Complementary info: One source providing a general answer and another providing a specific/detailed breakdown.
        - Omissions: One source mentioning a feature exists, and another not mentioning it at all.
        - Broad contextual differences that do not directly answer the specific QUESTION.
        
        CONTEXT (EACH SOURCE IS CLEARLY MARKED):
        {context_text}
        
        INSTRUCTIONS:
        1. Think step-by-step in the 'reasoning' field to evaluate if a true contradiction exists.
        2. Set 'has_conflict' to True ONLY if a strict factual contradiction exists based on the rules above.
        3. If True, you MUST copy the EXACT string found in the '--- SOURCE: [TEXT] ---' header. It is ABSOLUTELY MANDATORY to include the (Page X) or (Row Y) at the end of the string. 
        Format 'conflict_details' exactly using this template to ensure flawless source indexing:
           
           **⚠️ Conflict Detected:**
           - **[Source: <Exact name from the --- SOURCE: --- header>]**: "<copy the exact contradictory snippet>"
           - **[Source: <Exact name from the --- SOURCE: --- header>]**: "<copy the exact contradictory snippet>"
           
           *Summary*: <1 concise sentence explaining exactly why these facts are mutually exclusive>

        """


def status_classifier_prompt(question_text: str, answer_text: str, specs: List) -> str:
    """specs: objects with .column and .allowed_values (StatusSpec)."""
    blocks = []
    for s in specs:
        opts = "\n".join(f'    - "{v}"' for v in s.allowed_values)
        blocks.append(f'COLUMN: "{s.column}"\n  ALLOWED VALUES:\n{opts}')
    columns_text = "\n\n".join(blocks)

    return f"""You are a precise RFP compliance classifier.
Given a QUESTION and the analyst's already-grounded ANSWER, choose for EACH column below
the single allowed value that best reflects the ANSWER.

QUESTION:
{question_text}

ANALYST ANSWER (already grounded strictly in our knowledge base):
{answer_text}

COLUMNS TO CLASSIFY (return exactly one choice per column):
{columns_text}

RULES:
- Base your choice ONLY on the ANSWER above. Do NOT invent capabilities.
- If the ANSWER affirms the requirement is fully met -> the positive value (e.g. Yes / Applicable / Supported / Fully Supported).
- If only partially met / planned -> the partial or roadmap value if one exists, otherwise the closest.
- If the ANSWER says the information could not be found / needs a human / is unavailable,
  pick the 'Not Applicable' / 'N/A' / "Don't know" value if present; otherwise the most conservative negative value.
- 'column' MUST match a COLUMN header verbatim. 'chosen_value' MUST be copied VERBATIM from that column's allowed list."""


def pdf_extraction_prompt(rfp_text: str) -> str:
    return f"You are a Senior RFP Analyst. Find the questions/requirements. Maintain the order and provide the text exactly as it is.\nRFP TEXT:\n{rfp_text}"


def evaluation_judge_prompt(question: str, generated_answer: str, expected_answer: str) -> str:
    return f"""You are an expert AI evaluator grading an AI-generated answer against a Ground Truth expected answer.
    
    Question: {question}
    Generated Answer (RAG): {generated_answer}
    Expected Answer (Ground Truth): {expected_answer}
    
    CRITICAL RULES:
    1. If the 'Expected Answer' is strictly "Yes" or "No" without any additional information (or equivalent boolean, ignoring case/punctuation):
       - Evaluate if the 'Generated Answer' conceptually agrees with it.
       - If it AGREES: output exactly score: 100 and reasoning: "valid Answer but the reasoning is missing."
       - If it CONTRADICTS: output exactly score: 0 and reasoning: "invalid answer."
       - Be careful! In order to respond one of the upon answers, you have to make sure that the Expected Answer is just Yes/No(NOTHING ELSE). If the Expected Answer contains more information, even if it contains a Yes/No, you have to ignore the Yes/No and evaluate based on the rest of the information.
    2. Otherwise, evaluate semantic similarity. Score 0 to 100 based on how well the Generated Answer covers the facts in Expected Answer.Do NOT evaluate if the answer satisfies the user's Question!
    3. If the Generated Answer is "{FAIL_MSG_PREFIX}..." and the Expected Answer contains a real answer, the score MUST be 0.
    4.If the Generated Answer is "{FAIL_MSG_PREFIX}..." and the Expected Answer is also "{FAIL_MSG_PREFIX}...", the score MUST be 0.
    5. Provide brief, concise reasoning.
    6. NO CONTEXT LEAKAGE: Evaluate the Generated Answer EXCLUSIVELY against the Expected Answer. The Question is provided ONLY for context. Do NOT penalize the Generated Answer for missing any words, browsers, features, or requirements that are mentioned in the Question but are NOT present in the Expected Answer. If the Generated Answer covers the facts of the Expected Answer perfectly, the score MUST be 100.
    7. NO CONTEXT LEAKAGE & QUESTION CONTRADICTIONS: Your ONLY job is to compare the Generated Answer to the Expected Answer IGNORING THE QUESTION! Sometimes the Expected Answer itself deliberately contradicts the Question. THIS IS PERFECTLY FINE. Do NOT evaluate whether the Generated answer satisfies the question!
    8. SOURCE ORDERING INDEPENDENCE: Do NOT penalize the Generated Answer if it lists the exact same citations/sources but in a different order than the Expected Answer. The order of sources does not matter.
    """
