"""Exit codes and the error type commands raise."""

EXIT_SUCCESS = 0
EXIT_RUNTIME = 1
EXIT_USAGE = 2
EXIT_NOT_IMPLEMENTED = 3


class CliError(Exception):
    """A predictable failure that main() turns into a clean stderr message.

    ``code`` is the process exit code (see the table in specs/001-skeleton.md).
    """

    def __init__(self, message: str, code: int = EXIT_RUNTIME) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
