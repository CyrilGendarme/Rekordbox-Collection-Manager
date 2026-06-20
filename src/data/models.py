from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from pyrekordbox.db6.database import DjmdContent

@dataclass
class Track:
    """Represents a music track with all relevant metadata."""

    id: str
    name: str
    artist: str
    genre: Optional[str] = None
    key: Optional[str] = None  # Musical key (e.g., "Am", "C#m", "1A", "8B")
    bpm: Optional[float] = None
    tags: Optional[List[str]] = None
    rating: Optional[int] = None  # 0-5 stars
    file_path: Optional[str] = None
    album: Optional[str] = None
    year: Optional[int] = None
    comment: Optional[str] = None
    length: Optional[int] = None  # Duration in seconds
    position_marks: Optional[list] = None  # List of POSITION_MARK dicts

    def __post_init__(self):
        """Ensure tags and position_marks are always lists."""
        if self.tags is None:
            self.tags = []
        elif isinstance(self.tags, str):
            self.tags = [tag.strip() for tag in self.tags.split(",") if tag.strip()]
        if self.position_marks is None:
            self.position_marks = []

    @property
    def display_name(self) -> str:
        """Return formatted track name for display."""
        return f"{self.artist} - {self.name}"

    @staticmethod
    def _row_value(row: DjmdContent, key: str, default: Any = None) -> Any:
        """Read a value from a dict-like or attribute-like Rekordbox row."""
        if hasattr(row, "get"):
            return row.get(key, default)
        return getattr(row, key, default)

    @classmethod
    def from_djmdContent(cls, row: DjmdContent) -> "Track":
        """
        Build a Track from a Rekordbox djmdContent row.
        `row` can be a dict (e.g. sqlite row with keys).
        """

        bpm = cls._row_value(row, "BPM")

        return cls(
            id=str(cls._row_value(row, "ID")),
            name=cls._row_value(row, "Title") or "",
            artist=(
                cls._row_value(row, "SrcArtistName")
                or cls._row_value(row, "ArtistID")  # fallback (still an ID, not ideal)
                or "Unknown"
            ),
            genre=None,  # would require Genre lookup table join
            bpm=float(bpm) if bpm is not None else None,
            rating=cls._row_value(row, "Rating"),
            file_path=cls._row_value(row, "FolderPath")
            or cls._row_value(row, "rb_LocalFolderPath"),
            album=cls._row_value(row, "SrcAlbumName"),
            year=cls._row_value(row, "ReleaseYear"),
            comment=cls._row_value(row, "Commnt"),
            length=cls._row_value(row, "Length"),
            key=None,  # requires join with djmdKey
            tags=[cls._row_value(row, "Tag")] if cls._row_value(row, "Tag") else [],
        )
