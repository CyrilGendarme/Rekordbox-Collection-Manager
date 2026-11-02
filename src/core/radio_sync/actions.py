"""Push music files whose genre tag matches a regex to a VPS over SSH.

The genre comes from the Rekordbox XML export (falling back to file tags) and is
matched to the files of the local music folder by file name.

Only files missing on the VPS are transferred, to save bandwidth. Uploads go
to a temporary name and are renamed once complete, so a file present on the
VPS is always a full copy.

Files already on the VPS get their metadata updated from the local copy:
non-empty local tag values overwrite differing remote values (only the tag
text travels, not the audio). Remote files no longer present locally are
removed.
This step needs `python3` with `mutagen` on the VPS
(e.g. `sudo apt install python3-mutagen`); without it, pushing still works.

Uses Paramiko for username/password SSH authentication. An unknown server is
trusted on first use and its key saved to a known-hosts file of this app; a
changed key is rejected.

CLI usage (values default to the RADIO_* settings from .env):
    python -m src.core.radio_sync.actions [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import posixpath
import re
import shlex
import socket
import time
from dataclasses import dataclass, field
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import Callable, Optional
from urllib.parse import unquote

import paramiko

from src.core.radio_sync import tag_tools
from src.user_config import settings

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], None]

PARTIAL_SUFFIX = ".radiosync-part"
KNOWN_HOSTS_PATH = Path.home() / ".rekordbox_collection_manager_known_hosts"


class _TrustOnFirstUsePolicy(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self, client, hostname, key):
        client.get_host_keys().add(hostname, key.get_name(), key)
        client.save_host_keys(str(KNOWN_HOSTS_PATH))
        logger.info("Trusted new host %s (%s %s)", hostname, key.get_name(), key.get_fingerprint().hex())


@dataclass(frozen=True)
class VpsTarget:
    host: str
    remote_dir: str
    username: str
    password: str = field(repr=False)
    port: int = 22

    def connect(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        if KNOWN_HOSTS_PATH.exists():
            client.load_host_keys(str(KNOWN_HOSTS_PATH))
        client.set_missing_host_key_policy(_TrustOnFirstUsePolicy())
        client.connect(
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            look_for_keys=False,
            allow_agent=False,
        )
        return client


@dataclass
class SyncResult:
    matched: int = 0
    skipped: int = 0
    pushed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    # relative path -> tag keys changed (or that would be changed on a dry run)
    metadata_updated: dict[str, list[str]] = field(default_factory=dict)
    metadata_failed: list[tuple[str, str]] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    remove_failed: list[tuple[str, str]] = field(default_factory=list)


def find_matching_files(
    local_dir: Path,
    genre_pattern: str,
    extensions: tuple[str, ...] = settings.AUDIO_FILES_EXTENSIOINS,
) -> list[tuple[Path, dict[str, list[str]]]]:
    """Recursively list audio files whose genre matches, with their tags.

    Only files that exist in the Rekordbox XML export are considered. The genre
    comes from the XML (matched by file name, extension ignored) and replaces
    the file's genre tag.
    """
    regex = re.compile(genre_pattern, re.IGNORECASE)
    lowered_extensions = tuple(ext.lower() for ext in extensions)
    xml_tracks = _load_xml_tracks()
    matching = []
    for path in sorted(local_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in lowered_extensions:
            continue
        file_stem = path.stem.lower()
        xml_track = xml_tracks.get(file_stem)
        if not xml_track:
            logger.debug("File not in XML: %s (stem=%s)", path.name, file_stem)
            continue
        tags = tag_tools.read_tags(path)
        tags["genre"] = [xml_track["genre"]]
        if regex.search(" / ".join(tags.get("genre", []))):
            matching.append((path, tags))
            logger.debug("Matched file: %s (stem=%s, genre=%s)", path.name, file_stem, xml_track["genre"])
        else:
            logger.debug("File in XML but genre doesn't match pattern: %s (stem=%s, genre=%s)", path.name, file_stem, xml_track["genre"])
    logger.info("Found %d files matching genre pattern /%s/", len(matching), genre_pattern)
    return matching


def _load_xml_tracks() -> dict[str, dict[str, str]]:
    """Map lowercase file stem -> track info from the Rekordbox XML collection.
    
    Returns {file_stem: {"genre": genre_value}} for all tracks in the XML.
    Only tracks with both a genre and location are included.
    """
    xml_path = Path(settings.REKORDBOX_COLLECTION_TRACKS_XML_FILE_PATH)
    if not xml_path.is_file():
        logger.warning("Rekordbox XML not found: %s (no tracks will be synced)", xml_path)
        return {}
    tracks: dict[str, dict[str, str]] = {}
    for _, element in ET.iterparse(xml_path):
        if element.tag != "TRACK":
            continue
        genre = element.get("Genre")
        location = element.get("Location")
        if genre and location:
            path = unquote(location).replace("\\", "/")
            stem = PurePosixPath(path).stem.lower()
            logger.debug("XML track: location=%s, stem=%s, genre=%s", location, stem, genre)
            tracks.setdefault(stem, {"genre": genre})
        element.clear()
    logger.info("Loaded %d tracks from Rekordbox XML", len(tracks))
    return tracks




def _run_ssh_with_retry(
    target: VpsTarget,
    remote_command: str,
    stdin: str | None = None,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> str:
    """Run SSH command with retry logic for transient network failures.
    
    Retries on connection errors (DNS, connection refused, timeout).
    Permanent errors (exit code != 0, etc.) are not retried.
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            return _run_ssh(target, remote_command, stdin)
        except (socket.gaierror, socket.error, OSError, paramiko.ssh_exception.NoValidConnectionsError) as exc:
            last_error = exc
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)  # exponential backoff
                logger.warning(
                    "SSH command failed (attempt %d/%d), retrying in %.1f seconds: %s",
                    attempt + 1, max_retries, wait_time, exc
                )
                time.sleep(wait_time)
            else:
                logger.error("SSH command failed after %d attempts: %s", max_retries, exc)
    raise last_error


def _run_ssh(target: VpsTarget, remote_command: str, stdin: str | None = None) -> str:
    with target.connect() as client:
        stdin_stream, stdout, stderr = client.exec_command(remote_command)
        if stdin is not None:
            stdin_stream.write(stdin)
            stdin_stream.flush()
            stdin_stream.close()
        output = stdout.read().decode("utf-8", errors="replace")
        error = stderr.read().decode("utf-8", errors="replace")
        exit_status = stdout.channel.recv_exit_status()
    if exit_status != 0:
        raise RuntimeError(f"ssh failed: {error.strip()}")
    return output


def list_remote_files(target: VpsTarget) -> set[str]:
    """Relative posix paths of the complete files under the remote dir."""
    remote_dir = shlex.quote(target.remote_dir)
    output = _run_ssh_with_retry(
        target,
        f"mkdir -p {remote_dir} && "
        f"find {remote_dir} -type f ! -name '*{PARTIAL_SUFFIX}' -printf '%P\\n'",
    )
    return {line for line in output.splitlines() if line}


def _sftp_upload(target: VpsTarget, local_path: Path, remote_path: str) -> None:
    """Upload to a temporary name, then rename so partial uploads never look complete.
    
    Retries on transient network failures.
    """
    partial_path = remote_path + PARTIAL_SUFFIX
    max_retries = 3
    retry_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            with target.connect() as client:
                with client.open_sftp() as sftp:
                    sftp.put(str(local_path), partial_path)
            _run_ssh_with_retry(target, f"mv -f {shlex.quote(partial_path)} {shlex.quote(remote_path)}")
            return
        except (socket.gaierror, socket.error, OSError, paramiko.ssh_exception.NoValidConnectionsError) as exc:
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)
                logger.warning(
                    "SFTP upload failed (attempt %d/%d), retrying in %.1f seconds: %s",
                    attempt + 1, max_retries, wait_time, exc
                )
                time.sleep(wait_time)
            else:
                raise


def update_remote_metadata(
    target: VpsTarget,
    files: dict[str, dict[str, list[str]]],
    dry_run: bool = False,
) -> dict:
    """Update tags on VPS copies from local tags, in one ssh call.

    `files` maps remote paths to local tags. Returns the remote script's result:
    {"updated": {path: [keys]}, "errors": {path: message}}.
    """
    script = (
        Path(tag_tools.__file__).read_text(encoding="utf-8")
        + "\ntry:\n    import mutagen\nexcept ImportError:\n"
        + "    json.dump({'fatal': 'mutagen is not installed on the VPS"
        + " (e.g. sudo apt install python3-mutagen)'}, sys.stdout)\n"
        + "else:\n    run_remote()\n"
    )
    output = _run_ssh_with_retry(
        target,
        f"python3 -c {shlex.quote(script)}",
        stdin=json.dumps({"dry_run": dry_run, "files": files}),
    )
    result = json.loads(output)
    if "fatal" in result:
        raise RuntimeError(result["fatal"])
    return result


def sync_to_vps(
    local_dir: Path,
    target: VpsTarget,
    genre_pattern: str = "33",
    dry_run: bool = False,
    progress: Optional[ProgressCallback] = None,
    sync_metadata: bool = True,
) -> SyncResult:
    """Push matching audio files from `local_dir` to the VPS, skipping existing ones."""
    report = progress or (lambda message: logger.info(message))
    result = SyncResult()

    if not local_dir.is_dir():
        raise FileNotFoundError(f"Local directory not found: {local_dir}")

    report(f"Scanning {local_dir} for genre matching /{genre_pattern}/ ...")
    matching = find_matching_files(local_dir, genre_pattern)
    result.matched = len(matching)

    report(f"{len(matching)} matching file(s). Listing files on {target.host} ...")
    remote_files = list_remote_files(target)

    to_push: list[tuple[Path, str]] = []
    already_remote: dict[str, dict[str, list[str]]] = {}
    for local_path, tags in matching:
        relative = local_path.relative_to(local_dir).as_posix()
        if relative in remote_files:
            result.skipped += 1
            if tags:
                already_remote[relative] = tags
        else:
            to_push.append((local_path, relative))

    local_files = {local_path.relative_to(local_dir).as_posix() for local_path, _ in matching}
    to_remove = sorted(remote_files - local_files)
    report(
        f"{result.skipped} already on VPS, {len(to_push)} to push, "
        f"{len(to_remove)} no longer in collection."
    )
    if to_remove:
        logger.info("Files to remove from VPS: %s", to_remove)
        for file in to_remove:
            report(f"marked for removal: {file}")

    if sync_metadata and already_remote:
        _sync_metadata(target, already_remote, dry_run, result, report)

    if dry_run:
        result.pushed = [relative for _, relative in to_push]
        result.removed = to_remove
        return result

    for relative in to_remove:
        try:
            _remove_remote_file(target, posixpath.join(target.remote_dir, relative))
            result.removed.append(relative)
            report(f"removed: {relative}")
        except Exception as exc:
            report(f"Failed to remove: {relative} - {exc}")
            logger.error("Failed to remove %s: %s", relative, exc)
            result.remove_failed.append((relative, str(exc)))

    if not to_push:
        report(
            f"Done: {len(result.pushed)} pushed, {result.skipped} skipped, "
            f"{len(result.failed)} failed, {len(result.removed)} removed, "
            f"{len(result.remove_failed)} remove failures, "
            f"{len(result.metadata_updated)} metadata updated."
        )
        return result

    remote_dirs = sorted(
        {posixpath.join(target.remote_dir, posixpath.dirname(rel)) for _, rel in to_push}
    )
    _run_ssh_with_retry(target, "mkdir -p " + " ".join(shlex.quote(d) for d in remote_dirs))

    for index, (local_path, relative) in enumerate(to_push, start=1):
        report(f"[{index}/{len(to_push)}] pushing {relative}")
        try:
            _sftp_upload(target, local_path, posixpath.join(target.remote_dir, relative))
            result.pushed.append(relative)
        except Exception as exc:
            logger.error("Failed to push %s: %s", local_path, exc)
            result.failed.append((relative, str(exc)))

    report(
        f"Done: {len(result.pushed)} pushed, {result.skipped} skipped, "
        f"{len(result.failed)} failed, {len(result.removed)} removed, "
        f"{len(result.remove_failed)} remove failures, "
        f"{len(result.metadata_updated)} metadata updated."
    )
    return result


def _remove_remote_file(target: VpsTarget, remote_path: str) -> None:
    """Remove one file whose path was returned by the remote find command.
    
    Validates that the file is successfully removed. If the file exists but
    cannot be deleted, fails with a clear error message.
    """
    quoted_path = shlex.quote(remote_path)
    # Check if file exists first, then remove it, then verify it's gone
    # This ensures we catch permission/access errors clearly
    cmd = (
        f"if [ -f {quoted_path} ]; then "
        f"rm -- {quoted_path} && "
        f"if [ -f {quoted_path} ]; then "
        f"echo 'File still exists after rm'; exit 1; "
        f"fi; fi"
    )
    _run_ssh_with_retry(target, cmd)


def _sync_metadata(
    target: VpsTarget,
    already_remote: dict[str, dict[str, list[str]]],
    dry_run: bool,
    result: SyncResult,
    report: ProgressCallback,
) -> None:
    report(f"Comparing metadata of {len(already_remote)} file(s) already on VPS ...")
    by_remote_path = {
        posixpath.join(target.remote_dir, relative): relative for relative in already_remote
    }
    try:
        remote_result = update_remote_metadata(
            target,
            {remote: already_remote[relative] for remote, relative in by_remote_path.items()},
            dry_run=dry_run,
        )
    except Exception as exc:
        report(f"Metadata sync skipped: {exc}")
        result.metadata_failed.append(("*", str(exc)))
        return

    verb = "would update" if dry_run else "updated"
    for remote_path, keys in remote_result.get("updated", {}).items():
        relative = by_remote_path[remote_path]
        result.metadata_updated[relative] = keys
        report(f"{verb} metadata of {relative}: {', '.join(keys)}")
    for remote_path, error in remote_result.get("errors", {}).items():
        result.metadata_failed.append((by_remote_path[remote_path], error))
    report(f"Metadata: {len(result.metadata_updated)} remote file(s) {verb}.")


def target_from_settings(password: str) -> VpsTarget:
    return VpsTarget(
        host=settings.RADIO_VPS_HOST,
        remote_dir=settings.RADIO_VPS_REMOTE_DIR,
        username=settings.RADIO_VPS_USERNAME,
        port=settings.RADIO_VPS_PORT,
        password=password,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--local-dir", default=settings.RADIO_LOCAL_DIR)
    parser.add_argument("--host", default=settings.RADIO_VPS_HOST)
    parser.add_argument("--username", default=settings.RADIO_VPS_USERNAME)
    parser.add_argument("--port", type=int, default=settings.RADIO_VPS_PORT)
    parser.add_argument("--remote-dir", default=settings.RADIO_VPS_REMOTE_DIR)
    parser.add_argument("--genre-regex", default=settings.RADIO_GENRE_REGEX)
    parser.add_argument("--dry-run", action="store_true", help="List what would be pushed")
    parser.add_argument(
        "--no-metadata", action="store_true", help="Don't update metadata on the VPS"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not args.host or not args.username or not args.local_dir:
        parser.error("--host, --username and --local-dir are required (or set RADIO_* in .env)")

    import getpass

    result = sync_to_vps(
        Path(args.local_dir),
        VpsTarget(
            host=args.host,
            remote_dir=args.remote_dir,
            username=args.username,
            password=getpass.getpass("VPS password: "),
            port=args.port,
        ),
        genre_pattern=args.genre_regex,
        dry_run=args.dry_run,
        sync_metadata=not args.no_metadata,
    )
    if args.dry_run:
        for relative in result.pushed:
            print(f"would push: {relative}")
    for relative, error in result.failed:
        print(f"FAILED: {relative}: {error}")
    for relative, error in result.metadata_failed:
        print(f"METADATA FAILED: {relative}: {error}")
    for relative in result.removed:
        if args.dry_run:
            print(f"would remove: {relative}")
    for relative, error in result.remove_failed:
        print(f"REMOVE FAILED: {relative}: {error}")


if __name__ == "__main__":
    main()
