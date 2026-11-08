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

# Evaluator judge only (the agent uses the model sent with the upload). Pinned snapshot so scores stay
# comparable across runs.
JUDGE_MODEL = "gpt-4o-mini-2024-07-18"

# OpenAI prices ($ per 1,000,000 tokens): (input, output)
MODEL_PRICING = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o-mini-2024-07-18": (0.15, 0.60),
    "gpt-5-mini":  (0.25, 2.00),
}

# Cost is rounded at output only (Excel + API response); full precision internally.
COST_DECIMALS = 4
