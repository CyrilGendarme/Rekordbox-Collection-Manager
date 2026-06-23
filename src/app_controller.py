import logging
import threading
from typing import Callable, Dict, Iterable, List, Optional
from pathlib import Path

from .data.models import Track
from .data.rekrodbox_dao import RekordboxDAO
from .gui.main_window import MainWindow
from .gui.tabs.collection_filtering_tab import CollectionFilteringFeature
from .gui.tabs.memory_cues_tab import MemoryCuesFeature
from .gui.tabs.ripped_records_to_tracks_tab import RippedRecordsToTracksFeature
from .gui.tabs.samples_magnifier import SamplesMagnifierFeature
from .gui.tabs.tracks_info_completer_tab import TracksInfoCompleterFeature


class AppController:
    """Main application controller - orchestrates services and GUI."""

    _instance: "AppController | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(cls) -> "AppController":
        return cls()

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.logger = logging.getLogger(__name__)

        # Shared storage for features/tabs.
        self.track_store: Dict[str, List[Track]] = {"library": []}
        self.playlist_store: Dict[str, List[str]] = {}
        self._status_callback: Optional[Callable[[str], None]] = None
        self._collection_loaded_callbacks: List[Callable[[], None]] = []

        # Initialize GUI
        self.window = MainWindow(controller=self)
        self._register_features()
        self.window.set_status_callback(self._on_window_status_changed)

        # Auto-load tracks and playlists on startup
        self.refresh_collection()
        self._initialized = True

    def _register_features(self) -> None:
        """Register feature modules here to extend the app with more tabs."""
        self.features = [
            TracksInfoCompleterFeature(),
            CollectionFilteringFeature(),
            RippedRecordsToTracksFeature(),
            SamplesMagnifierFeature(),
            MemoryCuesFeature(),
        ]
        self.window.register_features(self.features, controller=self)

    # === STATUS CALLBACKS ===

    def register_status_callback(self, callback: Callable[[str], None]) -> None:
        """Expose a callback API so tabs/features can react to status changes."""
        self._status_callback = callback

    def get_status_callback(self) -> Callable[[str], None]:
        """Expose the status setter callback to other modules."""
        return self.set_status

    def _on_window_status_changed(self, message: str) -> None:
        if self._status_callback:
            self._status_callback(message)

    def set_status(self, message: str) -> None:
        self.window.set_status(message)

    def show_message_box(self, title: str, message: str, error: bool = False) -> None:
        if error:
            self.window.show_error(title, message)
        else:
            self.window.show_info(title, message)

    # === TRACK LOADING ===

    def get_tracks(self, key: str = "library") -> List[Track]:
        return list(self.track_store.get(key, []))

    def refresh_collection(self) -> None:

        def load_collection() -> None:
            """Load tracks/playlists using RekordboxDAO, then publish results to the UI."""
            try:
                self.set_status("Loading tracks and playlists...")
                dao = RekordboxDAO()

                tracks = dao.load_tracks_from_collection()
                playlists = dao.load_playlists_from_collection()

                self.track_store["library"] = tracks
                self.playlist_store["library"] = playlists
                self.set_status(
                    f"Loaded {len(tracks):,} tracks and {len(playlists):,} playlists"
                )
                self.call_collection_loaded_callbacks(tracks)

            except Exception as exc:
                self.logger.exception("Failed to refresh collection")
                self.set_status("Error loading collection")
                self.window.show_error(
                    "Load Error", f"Could not refresh collection: { str(exc)}"
                )

        """Reload tracks and playlists from disk in a background thread."""
        threading.Thread(target=load_collection, daemon=True).start()

    def register_collection_loaded_callbacks(
        self,
        callbacks: (
            Callable[[list[Track]], None] | Iterable[Callable[[list[Track]], None]]
        ),
    ) -> None:
        if callable(callbacks):
            self._collection_loaded_callbacks.append(callbacks)
        else:
            self._collection_loaded_callbacks.extend(callbacks)

    def clear_collection_loaded_callbacks(self) -> None:
        """Remove all registered collection-loaded callbacks."""
        self._collection_loaded_callbacks.clear()

    def call_collection_loaded_callbacks(self, data: list) -> None:
        """Invoke all registered callbacks with the same list argument."""
        for callback in self._collection_loaded_callbacks:
            try:
                callback(data)
            except Exception:
                self.logger.exception("Collection loaded callback failed")

    # === APPLICATION LIFECYCLE ===

    def run(self):
        """Run the application."""
        self.window.run()
