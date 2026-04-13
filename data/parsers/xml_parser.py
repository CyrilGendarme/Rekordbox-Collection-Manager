import xml.etree.ElementTree as ET
import logging
from pathlib import Path
from typing import List, Optional, Dict
import urllib.parse
import re

from ..models import Track
from utils.exceptions import ParseError


class XMLParser:
    """Parser for Rekordbox XML database (version 5 and earlier)."""

    def __init__(self, xml_path: Path):
        self.xml_path = xml_path
        self.logger = logging.getLogger(__name__)
        # Regex pattern to extract tags from comments: /* tag1 / tag2 / tag3 */
        self.tags_pattern = re.compile(r"/\*\s*(.+?)\s*\*/")

    def parse_playlists(self) -> List[Dict[str, object]]:
        """Extract all playlists/sets and their tracks from the XML database.
        Returns a list of dicts: { 'name': str, 'tracks': List[Track] }
        """
        try:
            tree = ET.parse(self.xml_path)
            root = tree.getroot()

            # Build a map of track ID to Track object
            track_map = {}
            collection = root.find(".//COLLECTION")
            if collection is None:
                raise ParseError("No COLLECTION element found in XML")
            for track_elem in collection.findall("TRACK"):
                track = self._element_to_track(track_elem)
                if track:
                    track_map[track.id] = track

            # Find all playlists (SETS)
            playlists = []
            playlists_root = root.find(".//PLAYLISTS")
            if playlists_root is not None:

                def walk_nodes(node, parent_name=None):
                    for child in node.findall("NODE"):
                        node_type = child.get("Type")
                        name = child.get("Name", "Unnamed Playlist")
                        if node_type == "1":  # Playlist
                            track_ids = [
                                trk.get("Key")
                                for trk in child.findall("TRACK")
                                if trk.get("Key")
                            ]
                            tracks = [
                                track_map[tid] for tid in track_ids if tid in track_map
                            ]
                            playlists.append({"name": name, "tracks": tracks})
                        elif node_type == "0":  # Folder
                            walk_nodes(child, parent_name=name)

                walk_nodes(playlists_root)
                self.logger.info(
                    f"Successfully parsed {len(playlists)} playlists from XML database"
                )
            else:
                self.logger.warning("No PLAYLISTS root found in XML database")
            return playlists
        except ET.ParseError as e:
            raise ParseError(f"XML parsing error: {e}")
        except FileNotFoundError:
            raise ParseError(f"XML file not found: {self.xml_path}")
        except Exception as e:
            raise ParseError(f"Error parsing XML playlists: {e}")

    def parse_tracks(self) -> List[Track]:
        """Extract all tracks from the XML database."""
        try:
            tree = ET.parse(self.xml_path)
            root = tree.getroot()

            tracks = []

            # Find COLLECTION element which contains tracks
            collection = root.find(".//COLLECTION")
            if collection is None:
                raise ParseError("No COLLECTION element found in XML")

            # Process each TRACK element
            for track_elem in collection.findall("TRACK"):
                track = self._element_to_track(track_elem)
                if track:
                    tracks.append(track)

            self.logger.info(
                f"Successfully parsed {len(tracks)} tracks from XML database"
            )
            return tracks

        except ET.ParseError as e:
            raise ParseError(f"XML parsing error: {e}")
        except FileNotFoundError:
            raise ParseError(f"XML file not found: {self.xml_path}")
        except Exception as e:
            raise ParseError(f"Error parsing XML database: {e}")

    def _clean_location(self, location: str) -> str:
        """Normalize a rekordbox file:// URL to a plain absolute path."""
        import urllib.parse
        try:
            location = urllib.parse.unquote(location)
        except Exception:
            pass

        # Strip all file:// variants
        if location.startswith("file://localhost/"):
            location = location[len("file://localhost/"):]
        elif location.startswith("file:///"):
            location = location[len("file:///"):]
        elif location.startswith("file://"):
            location = location[len("file://"):]

        # /C:/path → C:/path  (Windows absolute path after stripping scheme)
        if len(location) > 2 and location[0] == "/" and location[2] == ":":
            location = location[1:]

        # Normalise to backslashes on Windows
        from pathlib import PurePosixPath, PureWindowsPath
        import platform
        if platform.system().lower() == "windows":
            location = location.replace("/", "\\")

        return location

    def _element_to_track(self, track_elem: ET.Element) -> Optional[Track]:
        """Convert XML track element to Track object."""
        try:
            # DEBUG: Log ALL attributes and child elements for first 10 tracks
            track_id = track_elem.get("TrackID")
            if track_id and int(track_id) <= 10:
                self.logger.info("=" * 80)
                self.logger.info(f"RAW XML DATA FOR TRACK ID {track_id}")
                self.logger.info("=" * 80)

                # Log all XML attributes
                self.logger.info("ALL XML ATTRIBUTES:")
                for attr_name, attr_value in sorted(track_elem.attrib.items()):
                    self.logger.info(f"  {attr_name}: {attr_value!r}")

                # Log all child elements (tags, playlists, etc.)
                self.logger.info("\nALL CHILD ELEMENTS:")
                for child in track_elem:
                    self.logger.info(f"  Tag: {child.tag}")
                    self.logger.info(f"    Text: {child.text!r}")
                    self.logger.info(f"    Attributes: {dict(child.attrib)}")

                    # Log nested children (if any)
                    for subchild in child:
                        self.logger.info(f"      Nested Tag: {subchild.tag}")
                        self.logger.info(f"        Text: {subchild.text!r}")
                        self.logger.info(f"        Attributes: {dict(subchild.attrib)}")

                self.logger.info("=" * 80)

            # Extract attributes from XML
            name = track_elem.get("Name", "")
            artist = track_elem.get("Artist", "Unknown Artist")

            if not track_id or not name:
                return None

            # Decode file location
            location = track_elem.get("Location", "")
            if location:
                location = self._clean_location(location)

            # Parse BPM and convert to float
            bpm = None
            bpm_str = track_elem.get("AverageBpm")
            if not bpm_str:
                bpm_str = track_elem.get("Bpm")
            try:
                bpm = float(bpm_str) if bpm_str else None
            except (ValueError, TypeError):
                pass

            # Parse rating - Rekordbox XML uses 0-255 scale
            rating = None
            rating_str = track_elem.get("Rating")
            try:
                if rating_str:
                    raw_rating = int(rating_str)
                    # Rekordbox uses 0, 51, 102, 153, 204, 255 for 0-5 stars
                    # Convert to 0-5 scale
                    rating = round(raw_rating / 51.0)
                    rating = min(5, max(0, rating))  # Clamp to 0-5 range
            except (ValueError, TypeError):
                pass

            # Parse year
            year = None
            year_str = track_elem.get("Year")
            try:
                year = int(year_str) if year_str else None
            except (ValueError, TypeError):
                pass

            # Parse play time (in seconds)
            length = None
            playtime_str = track_elem.get("PlayTime")
            try:
                length = int(playtime_str) if playtime_str else None
            except (ValueError, TypeError):
                pass

            # Parse musical key
            key = track_elem.get("Tonality")
            if not key:
                key = track_elem.get("Key")

            # Parse genre
            genre = track_elem.get("Genre")

            # Parse tags from Comments field using regex
            # Format: "other text /* tag1 / tag2 / tag3 */ more text"
            tags = []
            comments = track_elem.get("Comments", "")

            if comments:
                # Use regex to find content between /* and */
                match = self.tags_pattern.search(comments)
                if match:
                    tags_string = match.group(1)  # Get the content between /* and */
                    # Split by "/" and clean up each tag
                    tags = [
                        tag.strip() for tag in tags_string.split("/") if tag.strip()
                    ]

                    # Debug log for first 10 tracks
                    if track_id and int(track_id) <= 10:
                        self.logger.info(f"Extracted tags from comments: {tags}")

            # Extract POSITION_MARKs (memory cues, hot cues, etc.)
            position_marks = []
            for pm in track_elem.findall("POSITION_MARK"):
                pm_dict = pm.attrib.copy()
                position_marks.append(pm_dict)

            return Track(
                id=track_id,
                name=name,
                artist=artist,
                genre=genre,
                key=key,
                bpm=bpm,
                rating=rating,
                file_path=location,
                album=track_elem.get("Album"),
                year=year,
                comment=comments,  # Store full comment for reference
                length=length,
                tags=tags,  # Now properly extracted from /* */ pattern
                position_marks=position_marks,
            )

        except Exception as e:
            self.logger.warning(f"Skipping malformed track: {e}")
            return None
