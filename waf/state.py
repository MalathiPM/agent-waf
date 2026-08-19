"""In-memory session state. Replaced by Redis before deployment."""
import time
from collections import defaultdict

_calls = defaultdict(list)      # session_id -> [(tool, timestamp)]


def record_call(session_id: str, tool: str) -> None:
    _calls[session_id].append((tool, time.time()))


def counts_last_minute(session_id: str) -> dict:
    cutoff = time.time() - 60
    out = defaultdict(int)
    for tool, ts in _calls[session_id]:
        if ts >= cutoff:
            out[tool] += 1
    return dict(out)


def tools_called(session_id: str) -> list:
    return [tool for tool, _ in _calls[session_id]]


def reset(session_id: str) -> None:
    _calls.pop(session_id, None)
