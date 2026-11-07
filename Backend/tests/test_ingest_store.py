"""ingest() and the upload endpoint against a real temp Chroma with fake embeddings (no network)."""
import asyncio

import openpyxl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app import ingestion, store
from app.api import router
from app.ingestion import IngestResult, IngestWriteError


class FakeEmbeddings(Embeddings):
    def __init__(self):
        self.calls = 0
        self.fail_on_call = None  # 1-based embed call that raises
        self.on_call = None

    def embed_documents(self, texts):
        self.calls += 1
        if self.on_call:
            self.on_call()
        if self.calls == self.fail_on_call:
            raise RuntimeError("simulated embedding failure")
        return [[float(len(t)), 1.0, 0.0] for t in texts]

    def embed_query(self, text):
        return [float(len(text)), 1.0, 0.0]


@pytest.fixture
def embeddings():
    return FakeEmbeddings()


@pytest.fixture
def db(tmp_path, monkeypatch, embeddings):
    monkeypatch.setenv("ANONYMIZED_TELEMETRY", "False")
    chroma_dir = str(tmp_path / "chroma")
    chroma = Chroma(persist_directory=chroma_dir, embedding_function=embeddings, collection_name="test_store")
    monkeypatch.setattr(store, "CHROMA_DIR", chroma_dir)
    monkeypatch.setattr(store, "_store", chroma)  # restored after the test
    monkeypatch.setattr(ingestion, "WRITE_BATCH_SIZE", 2)  # lets a write fail mid-file
    return chroma


@pytest.fixture
def load_calls(monkeypatch):
    calls = []
    load_file = ingestion._load_file

    async def counting_load(path, name):
        calls.append(name)
        return await load_file(path, name)

    monkeypatch.setattr(ingestion, "_load_file", counting_load)
    return calls


def make_xlsx(folder, name, rows, tag="v"):
    folder.mkdir(exist_ok=True)
    path = folder / name
    wb = openpyxl.Workbook()
    wb.active.append(["Question", "Answer"])
    for i in range(rows):
        wb.active.append([f"q{i}", f"{tag}{i}"])
    wb.save(path)
    return str(path)


def run(*paths):
    return asyncio.run(ingestion.ingest(list(paths)))


def versions(name):
    return ingestion._read_store_index().get(name, {})


def test_new_file(db, tmp_path):
    path = make_xlsx(tmp_path, "a.xlsx", 3)
    content_hash = ingestion._hash_file(path)

    assert run(path) == IngestResult(3, 0)

    stored = db.get(where={"source": "a.xlsx"}, include=["metadatas"])
    assert set(stored["ids"]) == {f"a.xlsx:{content_hash}:{i}" for i in range(3)}
    assert all(m["content_hash"] == content_hash and m["chunk_count"] == 3 for m in stored["metadatas"])


def test_unchanged_file_skips_without_parsing(db, embeddings, load_calls, tmp_path, capsys):
    path = make_xlsx(tmp_path, "a.xlsx", 3)
    run(path)
    load_calls.clear()
    embeddings.calls = 0

    assert run(path) == IngestResult(0, 1)

    assert not load_calls and embeddings.calls == 0
    assert versions("a.xlsx") == {ingestion._hash_file(path): (3, 3)}
    assert "unchanged" in capsys.readouterr().out


def test_crash_mid_write_reingests(db, embeddings, tmp_path):
    path = make_xlsx(tmp_path, "b.xlsx", 5)
    content_hash = ingestion._hash_file(path)

    embeddings.fail_on_call = 2
    with pytest.raises(IngestWriteError):
        run(path)
    assert versions("b.xlsx") == {content_hash: (2, 5)}

    embeddings.fail_on_call = None
    assert run(path) == IngestResult(5, 0)
    assert versions("b.xlsx") == {content_hash: (5, 5)}


def test_more_chunks_than_chunk_count_reingests(db, tmp_path):
    path = make_xlsx(tmp_path, "b.xlsx", 5)
    content_hash = ingestion._hash_file(path)
    run(path)
    extra = Document(page_content="extra", metadata={"source": "b.xlsx", "content_hash": content_hash, "chunk_count": 5})
    db.add_documents([extra], ids=["extra-chunk"])
    assert versions("b.xlsx") == {content_hash: (6, 5)}

    assert run(path) == IngestResult(5, 0)

    assert versions("b.xlsx") == {content_hash: (5, 5)}
    assert not db.get(ids=["extra-chunk"])["ids"]


def test_failed_replace_keeps_old_chunks(db, embeddings, tmp_path):
    old_hash = ingestion._hash_file(make_xlsx(tmp_path, "a.xlsx", 3))
    run(str(tmp_path / "a.xlsx"))
    embeddings.calls = 0
    new_path = make_xlsx(tmp_path, "a.xlsx", 4, tag="w")

    embeddings.fail_on_call = 2
    with pytest.raises(IngestWriteError):
        run(new_path)

    assert versions("a.xlsx") == {old_hash: (3, 3), ingestion._hash_file(new_path): (2, 4)}


def test_replace_deletes_old_chunks_only_after_success(db, embeddings, tmp_path):
    old_hash = ingestion._hash_file(make_xlsx(tmp_path, "a.xlsx", 3))
    run(str(tmp_path / "a.xlsx"))
    new_path = make_xlsx(tmp_path, "a.xlsx", 4, tag="w")
    old_during_writes = []
    embeddings.on_call = lambda: old_during_writes.append(versions("a.xlsx").get(old_hash))

    assert run(new_path) == IngestResult(4, 0)

    assert old_during_writes == [(3, 3), (3, 3)]
    assert versions("a.xlsx") == {ingestion._hash_file(new_path): (4, 4)}


def test_stale_old_hash_cleaned_on_skip(db, load_calls, tmp_path, monkeypatch):
    old_hash = ingestion._hash_file(make_xlsx(tmp_path, "c.xlsx", 2))
    run(str(tmp_path / "c.xlsx"))
    new_path = make_xlsx(tmp_path, "c.xlsx", 3, tag="w")
    new_hash = ingestion._hash_file(new_path)

    with monkeypatch.context() as m:
        m.setattr(db, "delete", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("simulated delete failure")))
        with pytest.raises(IngestWriteError):
            run(new_path)
    assert versions("c.xlsx") == {old_hash: (2, 2), new_hash: (3, 3)}
    load_calls.clear()

    assert run(new_path) == IngestResult(0, 1)

    assert not load_calls
    assert versions("c.xlsx") == {new_hash: (3, 3)}


def test_legacy_file_skips_and_keeps_chunks(db, embeddings, load_calls, tmp_path, capsys):
    legacy = [Document(page_content=f"old{i}", metadata={"source": "legacy.xlsx"}) for i in range(2)]
    db.add_documents(legacy, ids=["l0", "l1"])
    embeddings.calls = 0

    assert run(make_xlsx(tmp_path, "legacy.xlsx", 3)) == IngestResult(0, 1)

    assert not load_calls and embeddings.calls == 0
    assert versions("legacy.xlsx") == {None: (2, 0)}
    assert "legacy" in capsys.readouterr().out


def test_same_name_different_content_in_one_run_keeps_last(db, load_calls, tmp_path):
    first = make_xlsx(tmp_path / "one", "dup.xlsx", 2)
    second = make_xlsx(tmp_path / "two", "dup.xlsx", 3, tag="w")

    assert run(first, second) == IngestResult(5, 0)

    assert load_calls == ["dup.xlsx", "dup.xlsx"]
    assert versions("dup.xlsx") == {ingestion._hash_file(second): (3, 3)}


def test_same_file_twice_in_one_run_parses_once(db, load_calls, tmp_path):
    path = make_xlsx(tmp_path, "dup.xlsx", 2)

    assert run(path, path) == IngestResult(2, 1)

    assert load_calls == ["dup.xlsx"]
    assert versions("dup.xlsx") == {ingestion._hash_file(path): (2, 2)}


# --- Upload endpoint. A bare app: the real one's lifespan would ingest Backend/data/.
@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def as_upload(path, name):
    with open(path, "rb") as f:
        return ("files", (name, f.read()))


def test_upload_unchanged_file_skips(db, client, tmp_path):
    path = make_xlsx(tmp_path, "d.xlsx", 2)
    upload = as_upload(path, "d.xlsx")

    assert client.post("/api/documents/upload", files=[upload]).status_code == 200
    assert client.post("/api/documents/upload", files=[upload]).status_code == 200

    assert versions("d.xlsx") == {ingestion._hash_file(path): (2, 2)}


def test_upload_two_same_named_files_keeps_last(db, client, load_calls, tmp_path):
    first = make_xlsx(tmp_path / "one", "dup.xlsx", 2)
    second = make_xlsx(tmp_path / "two", "dup.xlsx", 3, tag="w")

    response = client.post("/api/documents/upload", files=[as_upload(first, "dup.xlsx"), as_upload(second, "dup.xlsx")])

    assert response.status_code == 200
    assert load_calls == ["dup.xlsx"]  # both land on one temp path, so the second is unchanged
    assert versions("dup.xlsx") == {ingestion._hash_file(second): (3, 3)}


def test_upload_empty_file_is_400(db, client, tmp_path):
    path = tmp_path / "e.xlsx"
    openpyxl.Workbook().save(path)

    assert client.post("/api/documents/upload", files=[as_upload(path, "e.xlsx")]).status_code == 400


def test_upload_batch_with_xls_is_400_and_writes_nothing(db, client, load_calls, tmp_path):
    path = make_xlsx(tmp_path, "good.xlsx", 2)

    response = client.post("/api/documents/upload", files=[as_upload(path, "good.xlsx"), ("files", ("old.XLS", b"unused"))])

    assert response.status_code == 400
    assert "save as .xlsx" in response.json()["detail"]
    assert load_calls == []
    assert versions("good.xlsx") == {}


def test_upload_accepts_xlsm(db, client, tmp_path):
    path = make_xlsx(tmp_path, "macro.xlsm", 2)

    assert client.post("/api/documents/upload", files=[as_upload(path, "macro.xlsm")]).status_code == 200
    assert versions("macro.xlsm") == {ingestion._hash_file(path): (2, 2)}


def test_startup_ingest_logs_stray_xls(db, tmp_path, capsys):
    (tmp_path / "old.xls").write_bytes(b"unused")
    make_xlsx(tmp_path, "macro.xlsm", 2)

    asyncio.run(ingestion.ingest_local_directory(str(tmp_path)))

    out = capsys.readouterr().out
    assert "Could not load 'old.xls'" in out and "Unsupported file type" in out
    assert versions("old.xls") == {}
    assert versions("macro.xlsm") != {}
