import os

# Backend/ (parent of this file's app/ folder), regardless of where the server is started
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db")
DATA_DIR = os.path.join(BASE_DIR, "data")
COLLECTION_NAME = "knowledge_base"

# Excel formats we can read (openpyxl). Legacy .xls is rejected with a 400 in api.py.
EXCEL_EXTENSIONS = (".xlsx", ".xlsm")

# Message the agent returns when the knowledge base has no answer.
# Compared literally across the backend — change with care.
FAIL_MSG_PREFIX = "I couldn't find a corresponding answer"
FAIL_MSG = FAIL_MSG_PREFIX + ". Please provide a human to answer the question!"
# Wording before step 5c: still in old files (eval set, past RFPs). Recognised, never written.
OLD_FAIL_MSG_PREFIX = "I couldn't be able to find a corresponding answer"

# Draft loop (citation check + judge share it): up to MAX_REVISIONS + 1 drafts, then FAIL_MSG.
MAX_REVISIONS = 2

# Draft retriever (MMR). Why lambda 0.7: docs/SPEC.md decision 4.
RETRIEVAL_K = 5
RETRIEVAL_FETCH_K = 20
MMR_LAMBDA = 0.7

# Extra ChatOpenAI settings per model: the one place for them, used by every agent LLM call (model selected
# in the UI) and by the evaluator judge. A model must be listed here to be used.
MODEL_SETTINGS = {
    "gpt-4o-mini": {"temperature": 0},
    "gpt-4o-mini-2024-07-18": {"temperature": 0},
    "gpt-5-mini": {"temperature": 0},
    # No dated snapshot exists (OpenAI model page, 2026-11-08). Reasoning model: temperature 0 is rejected
    # at the default effort. Effort "none" missed opposite Yes/No verdicts in a probe; "low" caught them.
    "gpt-6-luna": {"reasoning_effort": "low"},
}

# Evaluator judge only (the agent uses the model sent with the upload); a key of MODEL_SETTINGS. Use a dated
# snapshot where one exists, so scores stay comparable across runs.
JUDGE_MODEL = "gpt-6-luna"  # gpt-4o-mini misuses generated_verdict (eval/RESULTS.md)

# OpenAI prices ($ per 1,000,000 tokens): (input, output)
MODEL_PRICING = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o-mini-2024-07-18": (0.15, 0.60),
    "gpt-6-luna": (0.10, 0.50),
    "gpt-5-mini":  (0.25, 2.00),
}

# Cost is rounded at output only (Excel + API response); full precision internally.
COST_DECIMALS = 4
