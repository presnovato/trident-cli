"""Human vs ``--json`` output, and the UTF-8 console setup.

Commands never call ``print`` for results: they hand data to ``emit``. Errors
and diagnostics always go to stderr, so stdout can be piped into ``jq``.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

_JSON_MODE = False
_STREAM_STATE: dict[str, Any] = {}


def reset() -> None:
    """Reset the JSON flag. Called by main() so runs stay independent."""
    global _JSON_MODE
    _JSON_MODE = False


def set_json(enabled: bool) -> None:
    global _JSON_MODE
    _JSON_MODE = bool(enabled)


def is_json() -> bool:
    return _JSON_MODE


def _is_utf8(encoding: str | None) -> bool:
    if not encoding:
        return False
    return encoding.lower().replace("-", "") == "utf8"


def setup_streams() -> dict[str, Any]:
    """Force UTF-8 on stdout/stderr, recording the encodings before/after.

    PowerShell 5.1 otherwise garbles Cyrillic and emoji. The recorded state is
    surfaced by ``trident doctor``.
    """
    # stdin too: text piped into ``trident log`` must decode as UTF-8 even
    # when the installed command runs without PYTHONUTF8 (PowerShell 5.1).
    for name, stream in (("stdin", sys.stdin), ("stdout", sys.stdout), ("stderr", sys.stderr)):
        before = getattr(stream, "encoding", None)
        _STREAM_STATE[f"{name}_before"] = before
        if not _is_utf8(before):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
            except Exception:
                pass
        _STREAM_STATE[f"{name}_after"] = getattr(stream, "encoding", None)
    return dict(_STREAM_STATE)


def stream_state() -> dict[str, Any]:
    return dict(_STREAM_STATE)


def emit(data: Any, render: Callable[[Any], str]) -> None:
    """Print a result: JSON in ``--json`` mode, otherwise ``render(data)``."""
    if _JSON_MODE:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render(data))


def error(message: str) -> None:
    """Write a diagnostic or error to stderr."""
    print(message, file=sys.stderr)


def prompt(message: str) -> None:
    """Write an interactive prompt to stderr without a trailing newline."""
    print(message, end="", file=sys.stderr, flush=True)
