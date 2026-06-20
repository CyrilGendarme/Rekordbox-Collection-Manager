import logging
import sys
from typing import List, Optional, Callable
from pathlib import Path
from ...data.rekordbox_repository import RekordboxRepository
from ...data.models import Track
from ..exceptions import RekordboxError

EXCLUDED_GENRES = {"vocal sample", "sample", "loop samples"}


class TrackLoadingService:
    """Service for loading and filtering tracks from Rekordbox."""

    def __init__(self, custom_db_path: Optional[Path] = None):
        self.logger = logging.getLogger(__name__)
        self.repository: Optional[RekordboxRepository] = None
        self.custom_db_path = custom_db_path

    def load_tracks(
        self,
        on_success: Callable[[List[Track]], None],
        on_error: Callable[[str], None],
    ):
        """
        Load tracks from Rekordbox database.

        Args:
            on_success: Callback to call with loaded tracks
            on_error: Callback to call on error with error message
        """
        try:
            # Initialize repository if needed
            if not self.repository:
                self.repository = RekordboxRepository(custom_path=self.custom_db_path)

            # Load tracks
            tracks = self.repository.load_all_tracks()

            # Filter out sample tracks
            filtered_tracks = self._filter_sample_tracks(tracks)

            # Log filtering stats
            excluded_count = len(tracks) - len(filtered_tracks)
            if excluded_count > 0:
                self.logger.info(f"Filtered out {excluded_count} sample tracks")

            # Keep only tracks that do NOT have an artist
            filtered_tracks_2 = self._filter_tracks_with_artist(filtered_tracks)

            # Log filtering stats
            excluded_count = len(filtered_tracks) - len(filtered_tracks_2)
            if excluded_count > 0:
                self.logger.info(f"Filtered out {excluded_count} tracks with artist")

            on_success(filtered_tracks_2)

        except RekordboxError as e:
            on_error(str(e))
        except Exception as e:
            self.logger.exception("Unexpected error loading tracks")
            on_error(f"Unexpected error: {e}")

    def _filter_sample_tracks(self, tracks: List[Track]) -> List[Track]:
        """Filter out sample/loop tracks based on genre."""
        return [
            track
            for track in tracks
            if not track.genre or track.genre.lower().strip() not in EXCLUDED_GENRES
        ]

    def _filter_tracks_with_artist(self, tracks: List[Track]) -> List[Track]:
        """Keep only tracks that have an empty or missing artist."""
        return [
            track for track in tracks if not track.artist or not track.artist.strip()
        ]

    def get_playlists(self):
        """Return playlists/sets from the Rekordbox database using the correct parser."""
        if not self.repository:
            self.repository = RekordboxRepository(custom_path=self.custom_db_path)
            print(
                f"[DEBUG] RekordboxRepository created with db_path={self.custom_db_path}"
            )
        parser = self.repository.parser
        if hasattr(parser, "parse_playlists"):
            return parser.parse_playlists()
        return []
