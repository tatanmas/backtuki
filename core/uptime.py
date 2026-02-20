"""
Process start time for uptime calculation.
Set from CoreConfig.ready() when Django starts.
"""
import time

# Set when the app is ready (worker/process start)
_process_start_time: float | None = None


def set_start_time() -> None:
    global _process_start_time
    if _process_start_time is None:
        _process_start_time = time.time()


def get_uptime_seconds() -> float | None:
    """Seconds since process start, or None if not set."""
    if _process_start_time is None:
        return None
    return time.time() - _process_start_time
