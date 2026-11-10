import collections
import glob
import os
import sqlite3

from app.config import BASE_DIR, DATA_DIR
from app.ingestion import _hash_file

SNAPSHOT_DB = os.path.join(BASE_DIR, "kb_snapshot", "chroma_db", "chroma.sqlite3")


def test_snapshot_matches_data_folder():
    # Read-only: the baked image skips startup ingest only if every data/ file is in the snapshot with its current hash.
    con = sqlite3.connect(f"file:{SNAPSHOT_DB}?mode=ro", uri=True)
    rows = con.execute(
        "select id, key, string_value from embedding_metadata where key in ('source', 'content_hash')"
    ).fetchall()
    con.close()
    meta = collections.defaultdict(dict)
    for i, k, v in rows:
        meta[i][k] = v
    stored = {(m["source"], m["content_hash"]) for m in meta.values()}
    expected = {(os.path.basename(f), _hash_file(f)) for f in glob.glob(os.path.join(DATA_DIR, "*"))}
    assert stored == expected
