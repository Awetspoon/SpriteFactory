"""Shared processing errors that do not depend on UI or filesystem state."""


class ProcessingUnavailable(RuntimeError):
    """Raised when an optional processing dependency is unavailable."""


class ProcessingError(RuntimeError):
    """Raised when image processing cannot produce a valid result."""
