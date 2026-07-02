class GoMcKeeError(Exception):
    """Base error for Go McKee plugin failures."""

class ValidationError(GoMcKeeError):
    """Raised when canonical JSON references are invalid."""
