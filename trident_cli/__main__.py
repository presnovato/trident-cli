"""``python -m trident_cli`` and the installed ``trident`` entry point."""

from __future__ import annotations

import sys

from trident_cli.cli import main as _main


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return the exit code (testable)."""
    return _main(argv)


def run() -> None:
    """Console-script entry point: run and exit."""
    sys.exit(main())


if __name__ == "__main__":
    run()
