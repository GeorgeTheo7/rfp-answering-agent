"""Retrieval eval: does each retriever config return the chunks holding a question's expected fact?
No LLM calls: only the knowledge base (Backend/chroma_db) and one query embedding per question.
Run: .\\venv\\Scripts\\python eval\\retrieval_eval.py [--check-only]
Inputs: eval/eval_set_v2.xlsx (ID, Question, Split) + eval/retrieval_facts.json (matching rule in its "_about":
every phrase in "all", or one in "any", must appear in the retrieved chunks' combined text, case-insensitive,
after removing '**' and collapsing whitespace). First checks that every phrase occurs in some chunk of the
knowledge base; stops (exit 1) if not, since a fact that cannot match would count as a retrieval miss.
"""
import argparse
import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "Backend"))
from app.config import MMR_LAMBDA, RETRIEVAL_FETCH_K, RETRIEVAL_K, RETRIEVAL_SEARCH_TYPE

EVAL_SET = os.path.join(ROOT, "eval", "eval_set_v2.xlsx")
FACTS = os.path.join(ROOT, "eval", "retrieval_facts.json")
SPLITS = ("dev", "held_out")
NOT_EXCEL = {"file_type": {"$ne": "excel"}}



def current(store, vector):
    """What retrieve_node does with the current config (see nodes.retriever_settings)."""
    if RETRIEVAL_SEARCH_TYPE == "mmr":
        return store.max_marginal_relevance_search_by_vector(
            vector, k=RETRIEVAL_K, fetch_k=RETRIEVAL_FETCH_K, lambda_mult=MMR_LAMBDA)
    return store.similarity_search_by_vector(vector, k=RETRIEVAL_K)


# name -> (store, query vector) -> chunks.
CONFIGS = {
    f"a: current config ({RETRIEVAL_SEARCH_TYPE} k={RETRIEVAL_K})": current,
    "b: similarity k=5": lambda s, v: s.similarity_search_by_vector(v, k=5),
    "c: similarity k=8": lambda s, v: s.similarity_search_by_vector(v, k=8),
    "d: MMR k=8 fetch_k=20 λ=0.7": lambda s, v: s.max_marginal_relevance_search_by_vector(v, k=8, fetch_k=20, lambda_mult=0.7),
    "e: MMR k=5 fetch_k=20 λ=0.9": lambda s, v: s.max_marginal_relevance_search_by_vector(v, k=5, fetch_k=20, lambda_mult=0.9),
    "f: quota 4 policy PDF + 2 past-RFP (similarity)": lambda s, v: (
        s.similarity_search_by_vector(v, k=4, filter=NOT_EXCEL)
        + s.similarity_search_by_vector(v, k=2, filter={"file_type": "excel"})),
    "g: similarity k=6 (same chunk count as f)": lambda s, v: s.similarity_search_by_vector(v, k=6),
    "h: MMR k=5 fetch_k=20 λ=0.7 (previous default)": lambda s, v: s.max_marginal_relevance_search_by_vector(
        v, k=5, fetch_k=20, lambda_mult=0.7),
}


def normalize(text) -> str:
    return " ".join(str(text or "").replace("**", "").split()).casefold()


def phrases(fact: dict) -> list:
    return list(fact.get("all", [])) + list(fact.get("any", []))


def fact_found(fact: dict, texts) -> bool:
    """The _about rule over the combined text of the chunks."""
    joined = "\n".join(normalize(t) for t in texts)
    found = [normalize(p) in joined for p in fact.get("all", [])]
    if fact.get("any"):
        found.append(any(normalize(p) in joined for p in fact["any"]))
    return bool(found) and all(found)


def missing_phrases(facts: dict, kb_texts) -> list:
    """(question ID, phrase) for every phrase that occurs in no chunk of the knowledge base."""
    chunks = [normalize(t) for t in kb_texts]
    return [(qid, p) for qid, fact in facts.items() for p in phrases(fact)
            if not any(normalize(p) in c for c in chunks)]


def load_questions(path, ids) -> list:
    """[(id, question, split)] in sheet order, only IDs that have a fact."""
    df = pd.read_excel(path)
    return [(str(r["ID"]).strip(), str(r["Question"]), str(r["Split"]).strip())
            for _, r in df.iterrows() if str(r["ID"]).strip() in ids]


def is_past_rfp(doc) -> bool:
    return doc.metadata.get("file_type") == "excel"


def evaluate(store, embed, questions, facts, configs=CONFIGS) -> dict:
    """{config: {id: (fact found, past-RFP chunks retrieved)}}. One embedding per question."""
    vectors = {qid: embed(text) for qid, text, _ in questions}
    return {name: {qid: (fact_found(facts[qid], [d.page_content for d in docs]), sum(map(is_past_rfp, docs)))
                   for qid, _, _ in questions
                   for docs in [retrieve(store, vectors[qid])]}
            for name, retrieve in configs.items()}


def report(results: dict, questions) -> str:
    split_of = {qid: split for qid, _, split in questions}
    n = {s: sum(v == s for v in split_of.values()) for s in SPLITS}
    out = [f"# Retrieval eval ({len(questions)} questions with a fact)", "",
           f"| Config | Recall | dev ({n['dev']}) | held_out ({n['held_out']}) | Past-RFP chunks / question | Misses |",
           "|---|---|---|---|---|---|"]
    for name, rows in results.items():
        hits = {qid for qid, (found, _) in rows.items() if found}
        per_split = [f"{sum(split_of[q] == s for q in hits)}/{n[s]}" for s in SPLITS]
        past = sum(c for _, c in rows.values()) / len(rows) if rows else 0
        misses = ", ".join(q for q, _, _ in questions if q not in hits) or "–"
        out.append(f"| {name} | {len(hits)}/{len(rows)} | {per_split[0]} | {per_split[1]} | {past:.1f} | {misses} |")
    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true", help="only check that every fact phrase is in the knowledge base")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    for var in ("LANGSMITH_TRACING", "LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING", "LANGCHAIN_TRACING_V2"):
        os.environ[var] = "false"
    from app.agent import nodes  # noqa: F401  (load_dotenv, like the app)
    from app.store import get_vectorstore

    with open(FACTS, encoding="utf-8") as f:
        facts = json.load(f)["facts"]
    store = get_vectorstore()
    kb_texts = store.get(include=["documents"])["documents"]
    missing = missing_phrases(facts, kb_texts)
    print(f"Sanity check: {sum(len(phrases(f)) for f in facts.values())} phrases, {len(kb_texts)} chunks.")
    for qid, phrase in missing:
        print(f"  MISSING {qid}: {phrase!r}")
    if missing:
        sys.exit(1)
    print("  all phrases found in the knowledge base")
    if args.check_only:
        return
    questions = load_questions(EVAL_SET, set(facts))
    print(report(evaluate(store, store.embeddings.embed_query, questions, facts), questions))


if __name__ == "__main__":
    main()
