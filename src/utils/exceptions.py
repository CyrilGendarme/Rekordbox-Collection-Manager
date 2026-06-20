class RekordboxError(Exception):
    """Base exception for Rekordbox-related errors."""

    pass


class DatabaseNotFoundError(RekordboxError):
    """Raised when Rekordbox database cannot be located."""

    pass


class DatabaseCorruptError(RekordboxError):
    """Raised when database file is corrupted or unreadable."""

    pass


class UnsupportedFormatError(RekordboxError):
    """Raised when database format is not supported."""

    pass


class ParseError(RekordboxError):
    """Raised when parsing database content fails."""

    pass
