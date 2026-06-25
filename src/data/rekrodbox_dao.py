from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote
from uuid import uuid4

from pyrekordbox import Rekordbox6Database, RekordboxXml

from pyrekordbox.db6.database import DjmdContent
from pyrekordbox.db6.tables import DjmdCue
from .models import Track
from src.user_config import settings

REKORDBOX_COLLECTION_TRACKS_XML_FILE_PATH = (
    settings.REKORDBOX_COLLECTION_TRACKS_XML_FILE_PATH
)


class _MissingMasterPlaylistsFilter(logging.Filter):
    """Filter out the known non-blocking missing masterPlaylists warning."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "No masterPlaylists6.xml found" not in record.getMessage()


class RekordboxDAO:
    """Small DAO wrapper around Rekordbox6Database."""

    _instance: "RekordboxDAO | None" = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        key: str = "",
        unlock: bool = True,
    ):
        # Prevent re-initialization on every call
        if getattr(self, "_initialized", False):
            self._ensure_db_session()
            return

        self._suppress_non_blocking_warnings()

        self.db = Rekordbox6Database(
            key=key,
            unlock=unlock,
        )

        self.xml = RekordboxXml(path=REKORDBOX_COLLECTION_TRACKS_XML_FILE_PATH)

        self._initialized = True

    def close(self) -> None:
        if getattr(self.db, "session", None) is not None:
            self.db.close()

    def _ensure_db_session(self) -> None:
        """Reopen DB session when singleton instance has previously been closed."""
        if getattr(self.db, "session", None) is None:
            self.db.open()

    def __enter__(self) -> "RekordboxDAO":
        self._ensure_db_session()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # FIXME? way too heavy for its purpose, but only solutions found so far
    def getTracksLocationFromXml(self) -> list[str]:
        """Return all track locations found in the Rekordbox XML file."""
        return [
            unquote(track["Location"].replace("file://localhost/", "")).replace(
                "\\", "/"
            )
            for track in self.xml.get_tracks()
        ]

    def add_audio_file_as_track(self, audio_file_path: str, **track_fields: Any) -> Any:
        """Add a local audio file as a new track in the Rekordbox collection."""
        path = Path(audio_file_path).expanduser().resolve()
        track = self.db.add_content(path, **track_fields)
        self.db.commit()
        return track

    def get_all_genres_from_collection(self) -> list[str]:
        """Return all genre names found in the collection."""
        result = self.db.get_genre()
        genres = result.all() if hasattr(result, "all") else result
        return sorted(
            {
                genre.Name
                for genre in genres
                if genre is not None and getattr(genre, "Name", None)
            }
        )

    def get_all_tags_from_collection(self) -> list[str]:
        """Return all tag names found in the collection.

        This method first tries the MyTag table and falls back to the content Tag field.
        """
        tags: set[str] = set()

        get_my_tag = getattr(self.db, "get_my_tag", None)
        if callable(get_my_tag):
            result = get_my_tag()
            my_tags = result.all() if hasattr(result, "all") else result
            tags.update(
                tag.Name
                for tag in my_tags
                if tag is not None and getattr(tag, "Name", None)
            )

        content_result = self.db.get_content()
        contents = (
            content_result.all() if hasattr(content_result, "all") else content_result
        )
        tags.update(
            content.Tag
            for content in contents
            if content is not None and getattr(content, "Tag", None)
        )

        return sorted(tags)

    def load_tracks_from_collection(self) -> list[Track]:
        """Return Rekordbox collection as Track objects, filtering invalid rows."""

        tracks: list[Track] = []

        # Used to ensure no DB trash are loaded
        tracks_location_from_xml = set(self.getTracksLocationFromXml())

        for row in self.get_tracks():

            # skip invalid records
            if (
                not str(row.Title).strip()
                or row.OrgFolderPath not in tracks_location_from_xml
            ):
                continue

            track = Track.from_djmdContent(row)
            tracks.append(track)

        return tracks

    def load_playlists_from_collection(self) -> list[str]:
        """Return playlist names from Rekordbox when the underlying API exposes them.

        The pyrekordbox API surface varies across versions, so this method tries a few
        common access patterns and falls back to an empty list if none are available.
        """
        playlist_getters = (
            "get_playlist",
            "get_playlists",
            "get_master_playlist",
            "get_master_playlists",
        )

        items: list[Any] = []
        for getter_name in playlist_getters:
            getter = getattr(self.db, getter_name, None)
            if not callable(getter):
                continue

            result = getter()
            items = result.all() if hasattr(result, "all") else result
            break

        if not items:
            direct_attrs = ("Playlists", "MasterPlaylists", "playlist", "playlists")
            for attr_name in direct_attrs:
                value = getattr(self.db, attr_name, None)
                if value:
                    items = value
                    break

        names: list[str] = []
        for item in items or []:
            name = getattr(item, "Name", None)
            if name:
                names.append(str(name))

        return sorted(dict.fromkeys(names))

    def get_track_genre(self, track_id: int | str) -> str:
        """Return the genre name of a track, if set."""
        content = self._get_track_by_id(track_id)
        if content is None:
            return ""

        genre_obj = getattr(content, "Genre", None)
        if genre_obj is not None and getattr(genre_obj, "Name", None):
            return str(genre_obj.Name)

        genre_name = getattr(content, "GenreName", None)
        return str(genre_name) if genre_name else ""

    def get_track_tags(self, track_id: int | str) -> list[str]:
        """Return all tags currently assigned to a track.

        This combines tags from the content `Tag` field and `MyTag` relations when
        available.
        """
        content = self._get_track_by_id(track_id)
        if content is None:
            return []

        tags: set[str] = set()

        raw_tag = getattr(content, "Tag", None)
        if raw_tag:
            for part in str(raw_tag).replace(";", ",").split(","):
                name = part.strip()
                if name:
                    tags.add(name)

        for attr in ("MyTags", "Tags"):
            relation = getattr(content, attr, None)
            if relation:
                for item in relation:
                    name = getattr(item, "Name", None)
                    if not name:
                        my_tag_obj = getattr(item, "MyTag", None)
                        name = getattr(my_tag_obj, "Name", None) if my_tag_obj else None
                    if name:
                        tags.add(str(name))

        return sorted(tags)

    def set_track_tags(self, track_id: int | str, tag_names: list[str]) -> Any:
        """Assign a list of tags to a track.

        The method always updates the `Tag` string field and will also synchronize
        `MyTag` relations when supported by the current pyrekordbox model objects.
        """
        content = self._get_track_by_id(track_id)
        if content is None:
            raise ValueError(f"Track not found for ID: {track_id}")

        cleaned = sorted({name.strip() for name in tag_names if name and name.strip()})

        if hasattr(content, "Tag"):
            content.Tag = ", ".join(cleaned)

        relation = getattr(content, "MyTags", None)
        if relation is not None:
            relation.clear()
            for idx, name in enumerate(cleaned, start=1):
                my_tag = self._get_or_create_my_tag(name)
                relation.append(
                    self._create_song_my_tag_link(content, my_tag, track_no=idx)
                )

        self.db.commit()
        return content

    def set_track_metadata_in_rekordbox(
        self,
        track_id: int | str,
        title: str,
        artist: str,
        album: str = "",
        label: str = "",
        year: int | None = None,
        genre: str = "",
        tags: list[str] | None = None,
    ) -> None:
        """Update core Rekordbox fields and tags for one track."""
        core_payload: dict[str, Any] = {
            "title": title,
            "artist": artist,
        }
        if album:
            core_payload["album"] = album
        if label:
            core_payload["label"] = label
        if year is not None:
            core_payload["year"] = year

        self.update_info_of_track(track_id, **core_payload)

        if genre:
            self.update_info_of_track(track_id, genre=genre)

        self.set_track_tags(track_id, tags or [])

    def update_track_metadata(
        self,
        track_id: int | str,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        year: Optional[int] = None,
        label: Optional[str] = None,
        genre: Optional[str] = None,
        bpm: Optional[float] = None,
    ) -> bool:
        """Update common track metadata fields and return a success flag."""
        try:
            fields: dict[str, Any] = {}
            if title is not None:
                fields["title"] = title
            if artist is not None:
                fields["artist"] = artist
            if album is not None:
                fields["album"] = album
            if year is not None:
                fields["year"] = year
            if label is not None:
                fields["label"] = label
            if genre is not None:
                fields["genre"] = genre
            if bpm is not None:
                fields["bpm"] = bpm

            self.update_info_of_track(track_id, **fields)
            return True
        except Exception:
            logging.getLogger(__name__).exception(
                "Failed to update track metadata in Rekordbox for track_id=%s",
                track_id,
            )
            return False

    def update_info_of_track(self, track_id: int | str, **fields: Any) -> Any:
        """Update one track with generic fields (year, label, album, etc.).

        Supported convenience keys:
        - year -> ReleaseYear
        - title -> Title
        - artist -> ArtistID (existing or created)
        - album -> AlbumID (existing or created)
        - genre -> GenreID (existing or created)
        - label -> LabelID (existing or created)

        Any other key is treated as a direct attribute on DjmdContent.
        """
        content = self._get_track_by_id(track_id)
        if content is None:
            raise ValueError(f"Track not found for ID: {track_id}")

        if "year" in fields:
            fields["ReleaseYear"] = fields.pop("year")
        if "bpm" in fields:
            bpm_value = fields.pop("bpm")
            fields["BPM"] = None if bpm_value in (None, "") else int(round(float(bpm_value) * 100.0))
        if "title" in fields:
            fields["Title"] = fields.pop("title")

        if "artist" in fields:
            artist_name = fields.pop("artist")
            artist = self._get_or_create_artist(artist_name)
            fields["ArtistID"] = artist.ID

        if "genre" in fields:
            genre_name = fields.pop("genre")
            genre = self._get_or_create_genre(genre_name)
            fields["GenreID"] = genre.ID

        if "label" in fields:
            label_name = fields.pop("label")
            label = self._get_or_create_label(label_name)
            fields["LabelID"] = label.ID

        if "album" in fields:
            album_name = fields.pop("album")
            artist_name = fields.get("ArtistName") or fields.get("artist_name")
            artist = None
            if artist_name:
                artist = self._get_or_create_artist(artist_name)
            album = self._get_or_create_album(album_name, artist=artist)
            fields["AlbumID"] = album.ID

        for key, value in fields.items():
            if not hasattr(content, key):
                raise ValueError(f"Unsupported field for DjmdContent: {key}")
            setattr(content, key, value)

        self.db.commit()
        return content

    def get_tracks(self, is_valid: Optional[callable] = None) -> list[DjmdContent]:
        """Return tracks in the Rekordbox collection matching the is_valid condition."""

        result = self.db.get_content()

        contents = result.all() if hasattr(result, "all") else result

        tracks = [
            content
            for content in contents
            if content is not None and getattr(content, "ID", None) is not None
        ]

        if is_valid is not None:
            tracks = list(filter(is_valid, tracks))

        # Optional: sort by Title for stable UI / exports
        tracks.sort(key=lambda t: (getattr(t, "Title", "") or "").lower())

        return tracks

    def _get_track_by_id(self, track_id: int | str) -> Any:
        result = self.db.get_content(ID=track_id)
        if hasattr(result, "first"):
            return result.first()
        return result

    def _get_or_create_artist(self, name: str) -> Any:
        if not name:
            raise ValueError("artist name cannot be empty")
        existing = self._one_or_none(self.db.get_artist(Name=name))
        return existing if existing is not None else self.db.add_artist(name=name)

    def _get_or_create_genre(self, name: str) -> Any:
        if not name:
            raise ValueError("genre name cannot be empty")
        existing = self._one_or_none(self.db.get_genre(Name=name))
        return existing if existing is not None else self.db.add_genre(name=name)

    def _get_or_create_label(self, name: str) -> Any:
        if not name:
            raise ValueError("label name cannot be empty")
        existing = self._one_or_none(self.db.get_label(Name=name))
        return existing if existing is not None else self.db.add_label(name=name)

    def _get_or_create_my_tag(self, name: str) -> Any:
        if not name:
            raise ValueError("tag name cannot be empty")

        get_my_tag = getattr(self.db, "get_my_tag", None)
        if not callable(get_my_tag):
            raise ValueError("MyTag table is not available in this Rekordbox database")

        existing = self._one_or_none(get_my_tag(Name=name))
        if existing is not None:
            return existing

        add_my_tag = getattr(self.db, "add_my_tag", None)
        if not callable(add_my_tag):
            raise ValueError(
                f"Tag '{name}' does not exist in Rekordbox and current API cannot create MyTag entries"
            )

        return add_my_tag(name=name)

    def _create_song_my_tag_link(
        self, content: Any, my_tag: Any, track_no: int = 1
    ) -> Any:
        relation_prop = content.__class__.MyTags.property
        link_cls = relation_prop.mapper.class_

        kwargs: dict[str, Any] = {
            "ContentID": content.ID,
            "MyTagID": my_tag.ID,
        }

        if hasattr(link_cls, "TrackNo"):
            kwargs["TrackNo"] = track_no
        if hasattr(link_cls, "ID") and hasattr(self.db, "generate_unused_id"):
            kwargs["ID"] = self.db.generate_unused_id(link_cls)
        if hasattr(link_cls, "UUID"):
            kwargs["UUID"] = str(uuid4())

        if hasattr(link_cls, "create"):
            link = link_cls.create(**kwargs)
        else:
            link = link_cls(**kwargs)

        if hasattr(link, "Content"):
            link.Content = content
        if hasattr(link, "MyTag"):
            link.MyTag = my_tag
        return link

    def _get_or_create_album(self, name: str, artist: Any = None) -> Any:
        if not name:
            raise ValueError("album name cannot be empty")
        existing = self._one_or_none(self.db.get_album(Name=name))
        if existing is not None:
            return existing
        return self.db.add_album(name=name, artist=artist)

    @staticmethod
    def _one_or_none(result: Any) -> Any:
        if result is None:
            return None
        if hasattr(result, "one_or_none"):
            return result.one_or_none()
        if hasattr(result, "first"):
            return result.first()
        if isinstance(result, (list, tuple)):
            return result[0] if result else None
        return result

    @staticmethod
    def _resolve_db_inputs(
        db_path: Optional[str],
        db_dir: str,
    ) -> tuple[Optional[str], str]:
        path_obj = Path(db_path).expanduser() if db_path else None
        dir_obj = Path(db_dir).expanduser() if db_dir else None

        if path_obj and path_obj.is_dir():
            dir_obj = path_obj
            path_obj = None

        if dir_obj and dir_obj.is_file() and dir_obj.name.lower() == "master.db":
            path_obj = dir_obj
            dir_obj = dir_obj.parent

        if path_obj and path_obj.is_file():
            if dir_obj is None:
                dir_obj = path_obj.parent
        elif dir_obj and dir_obj.exists():
            candidate = dir_obj / "master.db"
            if candidate.exists():
                path_obj = candidate
            else:
                candidates = list(dir_obj.rglob("master.db"))
                if candidates:
                    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                    path_obj = candidates[0]
                    dir_obj = path_obj.parent

        resolved_path = str(path_obj) if path_obj else None
        resolved_dir = str(dir_obj) if dir_obj else ""
        return resolved_path, resolved_dir

    @staticmethod
    def _suppress_non_blocking_warnings() -> None:
        filter_instance = _MissingMasterPlaylistsFilter()
        for logger_name in (
            "pyrekordbox.db6.database",
            "pyrekordbox.masterdb.database",
        ):
            logger = logging.getLogger(logger_name)
            if not any(
                isinstance(f, _MissingMasterPlaylistsFilter) for f in logger.filters
            ):
                logger.addFilter(filter_instance)
