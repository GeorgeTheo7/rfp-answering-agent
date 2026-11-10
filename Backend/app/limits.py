"""Input and run limits for the public demo (config.DEMO_MODE) + the model allow-list. Settings are read from
the config module at call time, so tests can monkeypatch them."""
import logging
import math
import os
import threading
import time
from collections import deque
from typing import Callable, Dict, List, Optional

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


# --- Run limits (analyze + evaluate) ---
logger = logging.getLogger("uvicorn.error")  # shown by uvicorn's default logging at INFO

HOUR = 3600
DAY = 86400


class RateLimitError(Exception):
    """Run limit reached (HTTP 429); retry_after in seconds."""

    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


def _minutes(seconds: int) -> str:
    minutes = math.ceil(seconds / 60)
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


class RunLimiter:
    """Per-IP sliding hour + one cap per UTC day across all clients. In memory and per process
    (run a single replica); thread-safe. A rejected attempt is not recorded."""

    def __init__(self, per_hour: int, daily_cap: int, clock: Callable[[], float] = time.time):
        self._per_hour = per_hour
        self._daily_cap = daily_cap
        self._clock = clock
        self._lock = threading.Lock()
        self._by_ip: Dict[str, deque] = {}
        self._day: Optional[int] = None
        self._day_count = 0

    def acquire(self, ip: str) -> int:
        """Records one run for ip and returns the runs it has left this hour; raises RateLimitError instead."""
        with self._lock:
            now = self._clock()
            day = int(now // DAY)  # UTC day number
            if day != self._day:
                self._day, self._day_count = day, 0
                # Drop IPs with no run in the last hour, so the dict does not grow forever
                self._by_ip = {k: q for k, q in self._by_ip.items() if q and q[-1] > now - HOUR}
            if self._day_count >= self._daily_cap:
                wait = math.ceil((day + 1) * DAY - now)
                raise RateLimitError(f"The public demo has reached its daily limit of {self._daily_cap} runs. "
                                     f"Please try again in {_minutes(wait)}.", wait)
            runs = self._by_ip.setdefault(ip, deque())
            while runs and runs[0] <= now - HOUR:
                runs.popleft()
            if len(runs) >= self._per_hour:
                wait = max(1, math.ceil(runs[0] + HOUR - now))
                raise RateLimitError(f"Public demo limit: {self._per_hour} runs per hour. "
                                     f"Please try again in {_minutes(wait)}.", wait)
            runs.append(now)
            self._day_count += 1
            return self._per_hour - len(runs)


_run_limiter: Optional[RunLimiter] = None
_run_limiter_lock = threading.Lock()


def run_limiter() -> RunLimiter:
    """Created on first use from config (tests replace limits._run_limiter)."""
    global _run_limiter
    with _run_limiter_lock:
        if _run_limiter is None:
            _run_limiter = RunLimiter(config.RATE_LIMIT_PER_HOUR, config.DAILY_RUN_CAP)
        return _run_limiter


def client_ip(request) -> str:
    """X-Real-IP, set by nginx from the rightmost X-Forwarded-For entry (the backend is only reachable through
    nginx); else the direct peer (local runs without nginx)."""
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


def acquire_run(request) -> None:
    """Demo mode: count one run for the client or raise RateLimitError. Call right before the graph."""
    if not config.DEMO_MODE:
        return
    ip = client_ip(request)
    try:
        remaining = run_limiter().acquire(ip)
    except RateLimitError as e:
        logger.info("Run rejected (429) for client %s %s: retry after %ss", ip, request.url.path, e.retry_after)
        raise
    logger.info("Run accepted for client %s %s: %s runs left this hour", ip, request.url.path, remaining)
