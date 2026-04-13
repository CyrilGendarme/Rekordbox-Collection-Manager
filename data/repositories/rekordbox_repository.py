import logging
import platform
from pathlib import Path
from typing import List, Optional
import sqlite3

from ..models import Track
from ..parsers.xml_parser import XMLParser
from utils.exceptions import (
    DatabaseNotFoundError,
    UnsupportedFormatError,
    RekordboxError,
    DatabaseCorruptError,
)


class RekordboxRepository:
    """Repository for accessing Rekordbox track data with automatic detection."""

    def __init__(self, custom_path: Optional[Path] = None):
        """Initialize repository with optional custom database path."""
        self.logger = logging.getLogger(__name__)
        self.db_path = custom_path or self._detect_database_path()

        # Validate database before creating parser
        if self.db_path and self.db_path.suffix.lower() == ".db":
            self._validate_sqlite_database()

        self.parser = self._create_parser()

    def _validate_sqlite_database(self):
        """Validate that the SQLite database is accessible and not encrypted."""
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            # Try to access sqlite_master table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
            cursor.fetchone()
            conn.close()

            self.logger.info("Database validation successful")

        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()

            if "encrypted" in error_msg or "file is not a database" in error_msg:
                raise DatabaseCorruptError(
                    "Database appears to be encrypted or corrupted. "
                    "Please ensure you're using an unencrypted Rekordbox database, "
                    "or export your library to XML format (File -> Export Collection in Rekordbox)."
                )
            else:
                raise DatabaseCorruptError(f"Cannot access database: {e}")

    def load_all_tracks(self) -> List[Track]:
        """Load all tracks from the Rekordbox database."""
        if not self.parser:
            raise RekordboxError("No compatible database parser available")

        self.logger.info(f"Loading tracks from: {self.db_path}")
        return self.parser.parse_tracks()

    def get_tracks_by_genre(self, genres: List[str]) -> List[Track]:
        """Filter tracks by specified genres."""
        all_tracks = self.load_all_tracks()
        genre_set = {genre.lower() for genre in genres}

        return [
            track
            for track in all_tracks
            if track.genre and track.genre.lower() in genre_set
        ]

    def get_tracks_by_bpm_range(self, min_bpm: float, max_bpm: float) -> List[Track]:
        """Filter tracks by BPM range."""
        all_tracks = self.load_all_tracks()

        return [
            track
            for track in all_tracks
            if track.bpm and min_bpm <= track.bpm <= max_bpm
        ]

    def get_database_info(self) -> dict:
        """Get information about the detected database."""
        return {
            "path": str(self.db_path),
            "type": "SQLite" if self.db_path.suffix.lower() == ".db" else "XML",
            "exists": self.db_path.exists() if self.db_path else False,
            "size": (
                self.db_path.stat().st_size
                if self.db_path and self.db_path.exists()
                else 0
            ),
        }

    def _detect_database_path(self) -> Optional[Path]:
        """Automatically detect Rekordbox database location."""
        system = platform.system().lower()

        if system == "windows":
            search_paths = self._get_windows_search_paths()
        elif system == "darwin":  # macOS
            search_paths = self._get_macos_search_paths()
        else:
            self.logger.warning(f"Unsupported operating system: {system}")
            return None

        for path in search_paths:
            if path.exists():
                self.logger.info(f"Found Rekordbox database at: {path}")
                return path

        raise DatabaseNotFoundError(
            "Could not locate Rekordbox database. "
            "Please ensure Rekordbox is installed and has been run at least once."
        )

    def _get_windows_search_paths(self) -> List[Path]:
        """Get potential Rekordbox database paths on Windows."""
        user_home = Path.home()

        return [
            # Rekordbox 6+ (SQLite)
            user_home / "AppData" / "Roaming" / "Pioneer" / "rekordbox" / "master.db",
            user_home / "AppData" / "Roaming" / "Pioneer" / "rekordbox6" / "master.db",
            Path("C:") / "Users" / "Public" / "Documents" / "rekordbox" / "master.db",
            # Rekordbox 5 and earlier (XML)
            user_home
            / "AppData"
            / "Roaming"
            / "Pioneer"
            / "rekordbox"
            / "rekordbox.xml",
            user_home / "Documents" / "rekordbox" / "rekordbox.xml",
            Path("C:")
            / "Users"
            / "Public"
            / "Documents"
            / "rekordbox"
            / "rekordbox.xml",
            # Alternative locations
            user_home / "AppData" / "Local" / "Pioneer" / "rekordbox" / "master.db",
            user_home / "AppData" / "Local" / "Pioneer" / "rekordbox" / "rekordbox.xml",
        ]

    def _get_macos_search_paths(self) -> List[Path]:
        """Get potential Rekordbox database paths on macOS."""
        user_home = Path.home()

        return [
            # Rekordbox 6+ (SQLite)
            user_home
            / "Library"
            / "Application Support"
            / "Pioneer"
            / "rekordbox"
            / "master.db",
            user_home
            / "Library"
            / "Application Support"
            / "Pioneer"
            / "rekordbox6"
            / "master.db",
            Path("/Users/Shared/rekordbox/master.db"),
            # Rekordbox 5 and earlier (XML)
            user_home
            / "Library"
            / "Application Support"
            / "Pioneer"
            / "rekordbox"
            / "rekordbox.xml",
            user_home / "Documents" / "rekordbox" / "rekordbox.xml",
            Path("/Users/Shared/rekordbox/rekordbox.xml"),
        ]

    def _create_parser(self) -> Optional[object]:
        """Create appropriate parser based on database file type."""
        if not self.db_path or not self.db_path.exists():
            return None

        file_extension = self.db_path.suffix.lower()


        if file_extension == ".xml":
            self.logger.info("Using XML parser")
            return XMLParser(self.db_path)
        else:
            raise UnsupportedFormatError(
                f"Unsupported database format: {file_extension}. "
                "Only and .xml files are supported."
            )
