from app.ingestion import IngestDecision, decide_ingest


def test_new_file_ingests():
    assert decide_ingest({}, "new") == IngestDecision("ingest")


def test_same_hash_complete_skips():
    assert decide_ingest({"new": (3, 3)}, "new") == IngestDecision("skip")


def test_same_hash_fewer_chunks_reingests():
    assert decide_ingest({"new": (2, 3)}, "new") == IngestDecision("ingest", delete_before=["new"])


def test_same_hash_more_chunks_reingests():
    assert decide_ingest({"new": (4, 3)}, "new") == IngestDecision("ingest", delete_before=["new"])


def test_different_hash_replaces_after_write():
    assert decide_ingest({"old": (3, 3)}, "new") == IngestDecision("ingest", delete_after=["old"])


def test_legacy_skips_without_deleting():
    assert decide_ingest({None: (3, 0)}, "new") == IngestDecision("skip")


def test_legacy_wins_over_hashed_chunks():
    assert decide_ingest({None: (3, 0), "new": (2, 2)}, "new") == IngestDecision("skip")


def test_stale_old_hash_cleaned_on_skip():
    assert decide_ingest({"old": (3, 3), "new": (2, 2)}, "new") == IngestDecision("skip", delete_after=["old"])


def test_stale_old_hash_kept_until_incomplete_reingest_succeeds():
    decision = decide_ingest({"old": (3, 3), "new": (1, 2)}, "new")
    assert decision == IngestDecision("ingest", delete_before=["new"], delete_after=["old"])
