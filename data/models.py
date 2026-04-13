from dataclasses import dataclass
from typing import List, Optional, Set, Tuple


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
