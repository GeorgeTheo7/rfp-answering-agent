import importlib.util
from pathlib import Path
from types import SimpleNamespace

_spec = importlib.util.spec_from_file_location(
    "retrieval_eval", Path(__file__).resolve().parents[2] / "eval" / "retrieval_eval.py")
retrieval_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(retrieval_eval)


def _doc(text, file_type="pdf"):
    return SimpleNamespace(page_content=text, metadata={"file_type": file_type})


def test_fact_found_all_any_normalisation_and_phrases_across_chunks():
    texts = ["Backups use **immutable  (write-once)**\nstorage.", "Kept 35 days."]
    assert retrieval_eval.fact_found({"all": ["IMMUTABLE (write-once) storage", "35 days"]}, texts)
    assert not retrieval_eval.fact_found({"all": ["immutable", "90 days"]}, texts)
    assert retrieval_eval.fact_found({"any": ["West Europe", "35 days"]}, texts)
    assert not retrieval_eval.fact_found({"any": ["West Europe"]}, texts)
    assert not retrieval_eval.fact_found({}, texts)


def test_missing_phrases_lists_phrases_in_no_chunk():
    facts = {"EV-01": {"all": ["27001:2022"]}, "EV-13": {"any": ["primary region is West Europe", "nowhere"]}}
    kb = ["Certified to ISO/IEC **27001:2022**.", "The primary region is   West Europe."]
    assert retrieval_eval.missing_phrases(facts, kb) == [("EV-13", "nowhere")]


class FakeStore:
    """Returns fixed chunks per query; records which search each config used."""
    def __init__(self, by_query):
        self.by_query, self.calls = by_query, []

    def similarity_search_by_vector(self, v, k, filter=None):
        self.calls.append(("sim", k, filter))
        docs = self.by_query[v]
        if filter == {"file_type": "excel"}:
            docs = [d for d in docs if d.metadata["file_type"] == "excel"]
        elif filter:
            docs = [d for d in docs if d.metadata["file_type"] != "excel"]
        return docs[:k]

    def max_marginal_relevance_search_by_vector(self, v, k, fetch_k, lambda_mult):
        self.calls.append(("mmr", k, lambda_mult))
        return self.by_query[v][:k][::-1]


def test_evaluate_and_report_recall_splits_past_rfp_counts_and_misses():
    store = FakeStore({
        "q1": [_doc("Row: Priority 1 within 30 minutes", "excel"), _doc("intro"), _doc("Priority 1 answer")],
        "q2": [_doc("unrelated", "excel"), _doc("unrelated", "excel"), _doc("x")],
    })
    questions = [("EV-14", "q1", "dev"), ("EV-45", "q2", "held_out")]
    facts = {"EV-14": {"all": ["Priority 1"]}, "EV-45": {"all": ["within 24 hours"]}}
    configs = {"sim2": lambda s, v: s.similarity_search_by_vector(v, k=2),
               "quota": retrieval_eval.CONFIGS["f: quota 4 policy PDF + 2 past-RFP (similarity)"]}

    results = retrieval_eval.evaluate(store, lambda text: text, questions, facts, configs)

    assert results["sim2"] == {"EV-14": (True, 1), "EV-45": (False, 2)}
    assert results["quota"] == {"EV-14": (True, 1), "EV-45": (False, 2)}
    assert ("sim", 4, {"file_type": {"$ne": "excel"}}) in store.calls and ("sim", 2, {"file_type": "excel"}) in store.calls
    text = retrieval_eval.report(results, questions)
    assert "| sim2 | 1/2 | 1/1 | 0/1 | 1.5 | EV-45 |" in text


def test_current_config_follows_retrieval_search_type(monkeypatch):
    from app.config import MMR_LAMBDA, RETRIEVAL_K
    current = retrieval_eval.CONFIGS[next(iter(retrieval_eval.CONFIGS))]
    store = FakeStore({"q": [_doc("a"), _doc("b")]})
    current(store, "q")
    assert store.calls == [("sim", RETRIEVAL_K, None)]  # default: similarity
    monkeypatch.setattr(retrieval_eval, "RETRIEVAL_SEARCH_TYPE", "mmr")
    current(store, "q")
    assert store.calls[-1] == ("mmr", RETRIEVAL_K, MMR_LAMBDA)
