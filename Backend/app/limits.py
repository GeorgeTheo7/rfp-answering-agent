"""Input limits for the public demo (config.DEMO_MODE) + the model allow-list. Settings are read from the
config module at call time, so tests can monkeypatch them."""
import os
from typing import List

import pymupdf

from app import config
from app.config import MODEL_SETTINGS


class LimitError(Exception):
    """A limit was exceeded; the message is shown to the user (HTTP 400)."""


def allowed_models() -> List[str]:
    """Models a client may select: DEMO_MODELS in demo mode, every MODEL_SETTINGS model otherwise."""
    if config.DEMO_MODE:
        return [m for m in config.DEMO_MODELS if m in MODEL_SETTINGS]
    return list(MODEL_SETTINGS)


def check_model(model: str) -> None:
    """Always on: an unknown model would otherwise fail per question deep in the graph."""
    if model not in allowed_models():
        raise LimitError(f"Model '{model}' is not available.")


def check_upload(path: str, file_ext: str) -> None:
    """Demo mode: file size, then PDF page count (PyMuPDF, no LLM). Call before the graph runs."""
    if not config.DEMO_MODE:
        return
    if os.path.getsize(path) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise LimitError(f"The file is larger than {config.MAX_UPLOAD_MB} MB (public demo limit).")
    if file_ext == ".pdf":
        try:
            with pymupdf.open(path) as doc:
                pages = doc.page_count
        except Exception as e:
            raise LimitError("The PDF could not be read.") from e
        if pages > config.MAX_PDF_PAGES:
            raise LimitError(f"The PDF has {pages} pages; the public demo allows up to {config.MAX_PDF_PAGES}.")


def check_question_count(count: int) -> None:
    """Demo mode: called after extraction, before any question is answered."""
    if config.DEMO_MODE and count > config.MAX_QUESTIONS:
        raise LimitError(f"The file has {count} questions; the public demo allows up to {config.MAX_QUESTIONS}.")
