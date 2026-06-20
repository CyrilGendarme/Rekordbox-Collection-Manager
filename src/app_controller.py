import logging
import threading
from typing import List, Dict, Any, Optional
from pathlib import Path

from .data.models import Track
from .gui.main_window import MainWindow
from .data.services.track_loading_service import TrackLoadingService
from .data.services.metadata_service import update_mp3_tags


class AppController:
    """Main application controller - orchestrates services and GUI."""

    def __init__(self, custom_db_path: Optional[Path] = None):
        self.logger = logging.getLogger(__name__)

        # Initialize services
        self.track_loader = TrackLoadingService(custom_db_path)
        self.db_reader = RekordboxDBReader()

        # Track storage
        self.tracks: List[Track] = []

        # Initialize GUI
        self.window = MainWindow()
        self._setup_callbacks()

        # Auto-load tracks and playlists on startup
        self.load_tracks()

    def _setup_callbacks(self):
        """Setup GUI callbacks."""
        self.window.on_load_tracks = self.load_tracks
        self.window.tracks_tab.on_validate = self._on_validate_tracks

    # === TRACK LOADING ===

    def load_tracks(self):
        """Load tracks from Rekordbox database (async)."""
        self.window.set_status("Loading tracks...")

        def load_worker():
            self.track_loader.load_tracks(
                on_success=lambda tracks: self.window.root.after(
                    0, self._on_tracks_loaded, tracks
                ),
                on_error=lambda error: self.window.root.after(
                    0, self._on_load_error, error
                ),
            )

        thread = threading.Thread(target=load_worker, daemon=True)
        thread.start()

    def _on_tracks_loaded(self, tracks: List[Track]):
        """Handle successful track loading."""
        self.tracks = tracks
        self.window.set_tracks(tracks)
        self.window.set_status(f"Loaded {len(tracks):,} tracks")

    def _on_load_error(self, error_message: str):
        """Handle track loading error."""
        self.window.set_status("Error loading tracks")
        self.window.show_error("Load Error", error_message)

    def _on_validate_tracks(self, updates: list):
        """Push edited metadata for every track to the Rekordbox SQLCipher database
        and write ID3 tags to the physical MP3 files."""
        try:
            if not self.db_reader.connect():
                self.window.show_error(
                    "Validate", "Could not connect to the Rekordbox database."
                )
                return

            # Build a quick lookup from track_id -> Track for file-path access
            track_by_id = {str(t.id): t for t in self.tracks}

            failed = []
            tag_failures = []
            for track_id, name, artist, album in updates:
                self.logger.info(
                    "VALIDATE update request: track_id=%s title=%r artist=%r album=%r",
                    track_id,
                    name,
                    artist,
                    album,
                )
                success = self.db_reader.update_track(
                    int(track_id),
                    title=name or None,
                    artist=artist or None,
                    album=album or None,
                )
                if not success:
                    failed.append(track_id)
                    continue

                # Update ID3 tags on the physical file
                track = track_by_id.get(str(track_id))
                if track and track.file_path:
                    ok = update_mp3_tags(
                        track.file_path,
                        title=name or None,
                        artist=artist or None,
                        album=album or None,
                    )
                    if not ok:
                        tag_failures.append(track_id)

            self.db_reader.disconnect()

            updated = len(updates) - len(failed)
            if not failed and not tag_failures:
                self.window.set_status(f"{updated} track(s) updated successfully.")
            elif tag_failures and not failed:
                self.window.set_status(
                    f"{updated} updated; {len(tag_failures)} ID3 tag write(s) skipped."
                )
            else:
                self.window.set_status(f"{updated} updated, {len(failed)} failed.")
                self.window.show_error(
                    "Validate",
                    f"{len(failed)} track(s) could not be updated: {failed}",
                )
        except Exception as exc:
            self.logger.exception("Error during batch validate")
            self.window.show_error("Validate", f"Error: {exc}")

    # === APPLICATION LIFECYCLE ===

    def run(self):
        """Run the application."""
        self.window.run()
