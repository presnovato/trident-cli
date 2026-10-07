"""The single source of time for the whole CLI.

Later phases must take the current time only from here; tests override it with
a monkeypatch fixture.
"""

from datetime import datetime, timezone


def now() -> datetime:
    """Return the current time as an aware UTC datetime."""
    return datetime.now(timezone.utc)
