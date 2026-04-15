"""
Thread-safe progress tracking for long-running scheduling algorithms.

Each algorithm receives a `report_progress(percent, message)` callback.
The ProgressTracker collects these updates and formats them as
Server-Sent Events (SSE) for real-time streaming to the frontend.
"""
import asyncio
import json
import threading
from typing import Optional


class ProgressTracker:
    """
    Collects progress updates from an algorithm running in a background thread
    and exposes them as an async generator of SSE-formatted strings.
    """

    def __init__(self):
        self._percent: float = 0.0
        self._message: str = "Initializing..."
        self._done: bool = False
        self._result: Optional[dict] = None
        self._error: Optional[str] = None
        self._lock = threading.Lock()
        self._event = asyncio.Event()

    # ── Called from the algorithm thread ──────────────────────────────────

    def report_progress(self, percent: float, message: str = ""):
        """Update current progress (0-100). Thread-safe."""
        with self._lock:
            self._percent = min(100.0, max(0.0, percent))
            if message:
                self._message = message
        # Wake up the async generator
        self._event.set()

    def finish(self, result: dict):
        """Mark the computation as complete with a result payload."""
        with self._lock:
            self._percent = 100.0
            self._done = True
            self._result = result
        self._event.set()

    def fail(self, error: str):
        """Mark the computation as failed."""
        with self._lock:
            self._done = True
            self._error = error
        self._event.set()

    # ── Called from the async endpoint ────────────────────────────────────

    async def stream_sse(self):
        """Async generator that yields SSE-formatted strings."""
        while True:
            # Wait for a signal from the algorithm thread
            await self._event.wait()
            self._event.clear()

            with self._lock:
                if self._error:
                    yield format_sse("error", {"error": self._error})
                    return

                if self._done and self._result is not None:
                    # Send final progress tick
                    yield format_sse("progress", {
                        "percent": 100,
                        "message": "Complete"
                    })
                    yield format_sse("result", self._result)
                    return

                yield format_sse("progress", {
                    "percent": round(self._percent, 1),
                    "message": self._message
                })


def format_sse(event_type: str, data: dict) -> str:
    """Format a dict as a Server-Sent Event string."""
    payload = json.dumps(data)
    return f"event: {event_type}\ndata: {payload}\n\n"
