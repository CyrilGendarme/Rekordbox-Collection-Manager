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
    label: Optional[str] = None
    year: Optional[int] = None
    comment: Optional[str] = None
    length: Optional[int] = None  # Duration in seconds
    position_marks: Optional[list] = None  # List of POSITION_MARK dicts
    org_folder_path: Optional[str] = None  # Original folder path
    play_count: Optional[int] = None  # Number of times the track has been played

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

        bpm = row.BPM

        # TODO : for now, fields are set with raw values, not actual references to Artist/Album/Tags IDs

        return cls(
            id=str(row.ID),
            name=row.Title,
            artist=row.ArtistName,
            genre=row.GenreName,
            bpm=bpm / 100.0,
            rating=row.Rating,
            file_path=row.FolderPath or row.rb_LocalFolderPath,
            org_folder_path=row.FolderPath,
            album=row.AlbumName,
            label=getattr(row, "LabelName", None),
            year=row.ReleaseYear,
            comment=row.Commnt,
            length=row.Length / 60.0,
            key=row.KeyName,
            tags=row.MyTagNames,
            play_count=row.DJPlayCount,
        )
