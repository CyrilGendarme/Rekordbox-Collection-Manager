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

    @classmethod
    def from_djmdContent(cls, row: DjmdContent) -> "Track":
        """
        Build a Track from a Rekordbox djmdContent row.
        `row` can be a dict (e.g. sqlite row with keys).
        """

        return cls(
            id=str(row.get("ID")),
            name=row.get("Title") or "",
            artist=(
                row.get("SrcArtistName")
                or row.get("ArtistID")  # fallback (still an ID, not ideal)
                or "Unknown"
            ),
            genre=None,  # would require Genre lookup table join
            bpm=float(row["BPM"]) if row.get("BPM") is not None else None,
            rating=row.get("Rating"),
            file_path=row.get("FolderPath") or row.get("rb_LocalFolderPath"),
            album=row.get("SrcAlbumName"),
            year=row.get("ReleaseYear"),
            comment=row.get("Commnt"),
            length=row.get("Length"),
            key=None,  # requires join with djmdKey
            tags=[row["Tag"]] if row.get("Tag") else [],
        )
