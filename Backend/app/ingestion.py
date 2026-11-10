import asyncio
import os
import re
import glob
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import openpyxl
import pandas as pd
from llama_parse import LlamaParse
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from app.config import DATA_DIR, EXCEL_EXTENSIONS
from app.store import get_vectorstore

# Chroma rejects larger single writes (limit ~5461); a big Excel can exceed it.
WRITE_BATCH_SIZE = 5000

class IngestWriteError(Exception):
    """Embedding/store operation failed; the run was stopped."""

@dataclass(frozen=True)
class IngestDecision:
    action: str  # "ingest" | "skip"
    delete_before: List[str] = field(default_factory=list)  # hashes to delete before writing
    delete_after: List[str] = field(default_factory=list)  # hashes to delete after a successful write

@dataclass(frozen=True)
class IngestResult:
    written: int  # chunks
    skipped: int  # files

def decide_ingest(stored: Dict[Optional[str], Tuple[int, int]], new_hash: str) -> IngestDecision:
    """What to do with a file. `stored` is the file's chunks in the store:
    {content_hash: (found, chunk_count)}, key None = chunks without a hash (legacy).
    Other hashes are always old, even on skip: a crash can leave them behind after a replace."""
    if None in stored:
        return IngestDecision("skip")
    old_hashes = [h for h in stored if h != new_hash]
    if new_hash not in stored:
        return IngestDecision("ingest", delete_after=old_hashes)
    found, chunk_count = stored[new_hash]
    if found != chunk_count:
        return IngestDecision("ingest", delete_before=[new_hash], delete_after=old_hashes)
    return IngestDecision("skip", delete_after=old_hashes)

def _read_store_index() -> Dict[str, Dict[Optional[str], Tuple[int, int]]]:
    """{source: {content_hash: (found, chunk_count)}} for every file in the store."""
    index = {}
    results = get_vectorstore().get(include=["metadatas"])
    for meta in results.get("metadatas") or []:
        if not meta or "source" not in meta:
            continue
        versions = index.setdefault(meta["source"], {})
        content_hash = meta.get("content_hash")
        found = versions.get(content_hash, (0, 0))[0]
        versions[content_hash] = (found + 1, meta.get("chunk_count", 0))
    return index

def _delete_hashes(filename: str, hashes: List[str]) -> None:
    for content_hash in hashes:
        where = {"$and": [{"source": filename}, {"content_hash": content_hash}]}
        ids = get_vectorstore().get(where=where, include=[])["ids"]
        for start in range(0, len(ids), WRITE_BATCH_SIZE):
            get_vectorstore().delete(ids[start:start + WRITE_BATCH_SIZE])

def _hash_file(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

# ==========================================
# HELPER FUNCTION FOR EXCEL INGESTION (ALL SHEETS)
# ==========================================
def process_excel_for_rag(file_path: str, filename: str) -> List[Document]:
    visible_sheets = None
    
    # 1. Attempt to find only VISIBLE sheets
    if file_path.lower().endswith(EXCEL_EXTENSIONS):
        try:
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            visible_sheets = [sheet.title for sheet in wb.worksheets if sheet.sheet_state == 'visible']
            wb.close()
        except Exception as e:
            print(f"[WARNING] Could not read visible sheets via openpyxl: {e}")
            pass

    # 2. Load with pandas (only visible if found, otherwise all)
    try:
        if visible_sheets:
            all_sheets = pd.read_excel(file_path, sheet_name=visible_sheets)
        else:
            all_sheets = pd.read_excel(file_path, sheet_name=None)
    except Exception as e:
        print(f"[ERROR] Pandas failed to read the file: {e}")
        return []

    chunks = []
    source_pattern = re.compile(r'\[Source:.*?\]', re.IGNORECASE)
    
    for sheet_name, df in all_sheets.items():
        for index, row in df.iterrows():
            text_parts = []
            for col in df.columns:
                col_lower = str(col).lower().strip()
                if col_lower not in ["source", "sources", "πηγές", "πηγή", "conflict", "conflicts"]:
                    val = row[col]
                    if pd.notna(val) and str(val).strip() != "":
                        clean_val = source_pattern.sub('', str(val))
                        clean_val = re.sub(r'\s+', ' ', clean_val).strip()
                        if clean_val:
                            text_parts.append(f"{col}: {clean_val}")
            
            text_content = "\n".join(text_parts)
            if text_content.strip():
                doc = Document(
                    page_content=text_content,
                    metadata={
                        "source": filename,
                        "sheet": sheet_name, 
                        "row": index + 2,  
                        "file_type": "excel"
                    }
                )
                chunks.append(doc)
    return chunks

async def _load_pdf(file_path: str, filename: str) -> List[Document]:
    llama_key = os.environ.get("LLAMA_CLOUD_API_KEY")
    if not llama_key:
        raise ValueError("Missing LLAMA_CLOUD_API_KEY (needed for PDFs)")

    parser = LlamaParse(api_key=llama_key, result_type="markdown", verbose=True)
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "Header 1"), ("##", "Header 2"), ("###", "Header 3")])
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=150)

    chunks = []
    parsed_docs = await parser.aload_data(file_path)
    for i, doc in enumerate(parsed_docs):
        md_chunks = markdown_splitter.split_text(doc.text)
        for chunk in md_chunks:
            chunk.metadata["source"] = filename
            chunk.metadata["page"] = i + 1
            chunk.metadata["file_type"] = "pdf"
        chunks.extend(text_splitter.split_documents(md_chunks))
    return chunks

async def _load_file(file_path: str, filename: str) -> List[Document]:
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext in EXCEL_EXTENSIONS:
        return await asyncio.to_thread(process_excel_for_rag, file_path, filename)
    if file_ext == '.pdf':
        return await _load_pdf(file_path, filename)
    raise ValueError(f"Unsupported file type '{file_ext}'")

def _write_file_chunks(filename: str, decision: IngestDecision, chunks: List[Document], ids: List[str]) -> None:
    """Sync store writes for one file (delete old, embed + add, delete stale); run in a worker thread."""
    _delete_hashes(filename, decision.delete_before)
    for start in range(0, len(chunks), WRITE_BATCH_SIZE):
        end = start + WRITE_BATCH_SIZE
        get_vectorstore().add_documents(chunks[start:end], ids=ids[start:end])
    _delete_hashes(filename, decision.delete_after)

async def ingest(file_paths: List[str]) -> IngestResult:
    """Loads, chunks and stores each file that decide_ingest says needs it, writing right
    after it is processed, so files already written survive a later failure.
    A file that can't be loaded is logged and skipped. A failed store operation stops the run
    (IngestWriteError): it is usually systemic (bad key, quota), and continuing would
    pay LlamaParse for files that can't be saved."""
    try:
        store_index = await asyncio.to_thread(_read_store_index)
    except Exception as e:
        print(f"[ERROR] Could not read the store, stopping ingestion: {type(e).__name__}: {e}")
        raise IngestWriteError("Could not read the store") from e

    total_written = 0
    total_skipped = 0
    for file_path in file_paths:
        filename = os.path.basename(file_path)
        try:
            content_hash = await asyncio.to_thread(_hash_file, file_path)
        except OSError as e:
            print(f"[ERROR] Could not read '{filename}': {type(e).__name__}: {e}")
            continue
        stored = store_index.get(filename, {})
        decision = decide_ingest(stored, content_hash)

        if decision.action == "skip":
            if None in stored:
                print(f"[SYSTEM] Skipped '{filename}': legacy chunks without a hash.")
            else:
                print(f"[SYSTEM] Skipped '{filename}': unchanged.")
            try:
                await asyncio.to_thread(_delete_hashes, filename, decision.delete_after)
            except Exception as e:
                print(f"[ERROR] Could not clean up '{filename}', stopping ingestion: {type(e).__name__}: {e}")
                raise IngestWriteError(f"Could not clean up '{filename}'") from e
            total_skipped += 1
            continue

        try:
            chunks = await _load_file(file_path, filename)
        except Exception as e:
            print(f"[ERROR] Could not load '{filename}': {type(e).__name__}: {e}")
            continue
        if not chunks:
            print(f"[ERROR] No content extracted from '{filename}'.")
            continue

        for chunk in chunks:
            chunk.metadata["content_hash"] = content_hash
            chunk.metadata["chunk_count"] = len(chunks)
        ids = [f"{filename}:{content_hash}:{i}" for i in range(len(chunks))]

        try:
            await asyncio.to_thread(_write_file_chunks, filename, decision, chunks, ids)
        except Exception as e:
            print(f"[ERROR] Could not store '{filename}', stopping ingestion: {type(e).__name__}: {e}")
            raise IngestWriteError(f"Could not store '{filename}'") from e

        store_index[filename] = {content_hash: (len(chunks), len(chunks))}
        total_written += len(chunks)
        print(f"[SYSTEM] Ingested '{filename}' ({len(chunks)} chunks).")
    return IngestResult(total_written, total_skipped)

async def ingest_local_directory(directory_path: str = DATA_DIR):
    if not os.path.exists(directory_path):
        os.makedirs(directory_path, exist_ok=True)
        print(f"[SYSTEM] Created folder '{directory_path}'.")
        return

    all_local_files = []
    # *.xls stays so a stray legacy file is logged as unsupported, not silently ignored.
    for ext in ["*.pdf", "*.xlsx", "*.xlsm", "*.xls"]:
        all_local_files.extend(glob.glob(os.path.join(directory_path, ext)))

    if not all_local_files: return

    print(f"[SYSTEM] Checking {len(all_local_files)} files in '{directory_path}'...")

    try:
        await ingest(all_local_files)
    except IngestWriteError as e:
        # The app still starts; files already written are skipped by hash on the next start.
        print(f"[ERROR] Startup ingestion stopped: {e}")
