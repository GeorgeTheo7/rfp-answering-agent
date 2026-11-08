import json
import operator
from enum import Enum
from typing import List, Dict, Annotated, NamedTuple, Optional
from typing_extensions import TypedDict
from pydantic import BaseModel, Field

# ==========================================
# 2. SCHEMAS (DATA MODELS)
# ==========================================
class Status(str, Enum):
    """Outcome of one question, set by code. Drives the colours in the UI and in Excel."""
    answered = "answered"
    not_found = "not_found"
    needs_review = "needs_review"  # last draft kept after max revisions
    error = "error"

class StatusSpec(BaseModel):
    column: str = ""
    allowed_values: List[str] = Field(default_factory=list)

# LLM-facing PDF extraction: only what the LLM reads from the text; code builds the Question.
class ExtractedQuestion(BaseModel):
    id: str = Field(description="A unique ID, e.g., 'Q1', '1a'")
    text: str = Field(description="The complete exact text of the question/requirement from start to finish.")
    category: str = Field(description="Must be ONE of the following: 'Security', 'Tech', 'Product'")

class RFPQuestions(BaseModel):
    questions: List[ExtractedQuestion]

class Question(BaseModel):
    id: str
    text: str
    category: str
    status_specs: List[StatusSpec] = Field(default_factory=list)  # Excel dropdown columns
    # Where the question was read from (Excel). None for PDFs.
    sheet: Optional[str] = None
    row_index: Optional[int] = None

# LLM-facing draft: only what the analyst decides; code builds the Answer.
# A comment, not a docstring: docstrings are sent to the LLM as the schema description.
class AnalystDraft(BaseModel):
    answer_text: str

class Answer(BaseModel):
    question_id: str
    question_text: str
    assigned_analyst: str
    answer_text: str
    sources_used: List[str] = Field(default_factory=list)  # rebuilt from inline citations in finalize
    conflicts: str = ""  
    review_note: str = ""  # why the agent doubts it (set by give_up); non-empty = needs_review
    cost: float = 0.0
    status_values_json: str = ""   # JSON map {column_header: chosen_value}; filled by classify_statuses
    # Copied from the Question by code (draft_node / error fallback).
    category: str = ""
    sheet: Optional[str] = None
    row_index: Optional[int] = None
    status: Status = Status.answered

    @property
    def status_values(self) -> Dict[str, str]:
        try:
            return json.loads(self.status_values_json or "{}")
        except Exception:
            return {}

# Schema for the constrained dropdown classifier (multi-column, one LLM call)
class StatusChoice(BaseModel):
    column: str = Field(description="The exact column header being classified, copied verbatim.")
    reasoning: str = Field(description="Brief: why this value best fits the answer.")
    chosen_value: str = Field(description="EXACTLY one value, copied verbatim from that column's allowed list.")

class StatusChoices(BaseModel):
    choices: List[StatusChoice]

# Schema for the Conflict Auditor (Strict CoT)
class ConflictDetection(BaseModel):
    reasoning: str = Field(description="Step-by-step analysis: Check if the documents state MUTUALLY EXCLUSIVE facts for the specific question. Differences in terminology or complementary info are NOT conflicts.")
    has_conflict: bool = Field(description="True ONLY if a strict, factual contradiction was found (e.g., Source A says 'Yes' and Source B says 'No', or SLAs are different numbers).")
    conflict_details: str = Field(description="If has_conflict=True, write the result STRICTLY as follows:\n- [SOURCE: Exact Source Name 1]: 'Exact Snippet'\n- [SOURCE: Exact Source Name 2]: 'Exact Snippet'\n*Reasoning:* Brief explanation of the conflict.\n\nIf has_conflict=False, leave it completely blank.")

class HallucinationEvaluation(BaseModel):
    reasoning: str = Field(description="Check each claim in the ANSWER against the CONTEXT, briefly.")
    has_hallucination: bool = Field(description="True if the answer contains information, procedures,assumption or locations NOT explicitly stated in the Context.")
    feedback: str = Field(description="If has_hallucination=True, explain exactly what was fabricated so the Analyst can fix it. If False, leave it blank.")

class RFPAnalyst(BaseModel):
    category_match: str
    name: str
    role_description: str
    tone: str

company_analysts = {
    "Security": RFPAnalyst(category_match="Security", name="Chief Information Security Officer (CISO)", role_description="You are responsible for data security, encryption, network architecture, and compliance for our products.", tone="Strict, legally accurate, evidence-based."),
    "Tech": RFPAnalyst(category_match="Tech", name="Lead IT System Architect", role_description="You design the technical architecture, APIs, databases, SLAs, and integrations with external systems for our company.", tone="Technical, analytical, practical."),
    "Product": RFPAnalyst(category_match="Product", name="Senior Product Manager", role_description="You know every function and feature of our software, from user experience to core capabilities.", tone="Customer-centric, clear, solutions-oriented.")
}

# ==========================================
# 4. LANGGRAPH STATES
# ==========================================
class QuestionAnsweringState(TypedDict):
    question: Question           
    retrieved_context: str       
    draft_answer: Answer         
    selected_model: str

class SourceRef(NamedTuple):
    """One retrieved chunk's location; `label` is the text of its '--- SOURCE: ---' header."""
    file: str
    sheet: str     # "" for PDFs and sheetless rows
    location: str  # "Page N" or "Row N"

    @property
    def label(self) -> str:
        return f"{self.file} - {self.sheet} ({self.location})" if self.sheet else f"{self.file} ({self.location})"

class QuestionState(TypedDict, total=False):
    """Question subgraph state (one question)."""
    question: Question
    selected_model: str
    analyst: RFPAnalyst
    context_text: str            # retrieved sources for draft + judge
    allowed_sources: List[SourceRef]  # sources in context_text, for citation validation
    attempt: int                 # drafts made so far
    feedback: str                # judge feedback for the next draft
    draft: Answer                # latest draft
    citations_valid: bool        # latest citation check
    has_hallucination: bool      # latest judge verdict
    review_note: str             # reason for the latest rejection (judge feedback or invalid citations)
    conflicts: str
    status_map: Dict[str, str]
    answer: Answer               # finalized (cost set by the caller)

class RFPGraphState(TypedDict):
    rfp_input_path: str         
    extracted_questions: List[Question] 
    completed_answers: Annotated[List[Answer], operator.add]
    final_answers: List[Answer]  # completed_answers in output order
    selected_model: str
