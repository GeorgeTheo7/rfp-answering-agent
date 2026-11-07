"""Debug runner: one RFP file (.xlsx/.xlsm/.pdf) through /api/rfp/analyze in-process, like eval/smoke.py.
Prints the agent log (draft/judge/citation lines), then id | status | question, answer, sources per row.
Real LLM calls. No app startup -> no startup ingest. No checks: read the output.
Run: .\\venv\\Scripts\\python eval\\run_rfp.py <file> [--model gpt-4o-mini]
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "Backend"))
sys.stdout.reconfigure(encoding="utf-8")
# Debug runs shouldn't send LangSmith traces (load_dotenv doesn't override these).
for var in ("LANGSMITH_TRACING", "LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING", "LANGCHAIN_TRACING_V2"):
    os.environ[var] = "false"

from fastapi.testclient import TestClient

from app.main import app

parser = argparse.ArgumentParser()
parser.add_argument("file")
parser.add_argument("--model", default="gpt-4o-mini")
args = parser.parse_args()

client = TestClient(app)  # no `with` -> lifespan (startup ingest) not run
with open(args.file, "rb") as f:
    r = client.post("/api/rfp/analyze", files={"file": (os.path.basename(args.file), f)}, data={"model": args.model})
r.raise_for_status()

print("\n=== RESULTS ===")
for row in r.json()["preview_data"]:
    print(f"{row['id']} | {row.get('status')} | {row['question'][:60]}")
    print(f"   A: {row['answer']}")
    print(f"   S: {row['sources']}")
