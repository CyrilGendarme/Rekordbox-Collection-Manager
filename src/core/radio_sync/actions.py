"""Push music files whose Rekordbox genre matches a regex to a VPS over SSH.

The genre comes from the Rekordbox collection (file tags are often stale). Each
matching track is paired by file name with a file under the local music folder.

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

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
    report: ProgressCallback = lambda message: None,
) -> list[tuple[Path, dict[str, list[str]]]]:
    """List files under `local_dir` whose Rekordbox genre matches, with their tags.

    Rekordbox tracks are paired with local files by file name (extension ignored);
    the Rekordbox genre replaces the genre tag so remote metadata follows it.
    """
    from src.data.rekrodbox_dao import RekordboxDAO

    regex = re.compile(genre_pattern, re.IGNORECASE)
    lowered_extensions = tuple(ext.lower() for ext in extensions)
    local_by_stem: dict[str, Path] = {}
    for path in sorted(local_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in lowered_extensions:
            local_by_stem.setdefault(path.stem.lower(), path)

    with RekordboxDAO() as dao:
        tracks = [
            track
            for track in dao.load_tracks_from_collection()
            if track.genre and track.file_path and regex.search(track.genre)
        ]

    matching: dict[Path, dict[str, list[str]]] = {}
    not_found = []
    for track in tracks:
        track_path = Path(track.file_path.replace("\\", "/"))
        local_path = local_by_stem.get(track_path.stem.lower())
        if local_path is None:
            not_found.append(track_path.name)
            continue
        tags = tag_tools.read_tags(local_path)
        tags["genre"] = [track.genre]
        matching[local_path] = tags

    if not_found:
        report(f"{len(not_found)} Rekordbox track(s) not found in {local_dir}:")
        for name in not_found[:20]:
            report(f"  missing: {name}")
    return sorted(matching.items())


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
    output = _run_ssh(
        target,
        f"mkdir -p {remote_dir} && "
        f"find {remote_dir} -type f ! -name '*{PARTIAL_SUFFIX}' -printf '%P\\n'",
    )
    return {line for line in output.splitlines() if line}


def _sftp_upload(target: VpsTarget, local_path: Path, remote_path: str) -> None:
    """Upload to a temporary name, then rename so partial uploads never look complete."""
    partial_path = remote_path + PARTIAL_SUFFIX
    with target.connect() as client:
        with client.open_sftp() as sftp:
            sftp.put(str(local_path), partial_path)
    _run_ssh(target, f"mv -f {shlex.quote(partial_path)} {shlex.quote(remote_path)}")


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
    output = _run_ssh(
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

    report(f"Reading Rekordbox genres matching /{genre_pattern}/ ...")
    matching = find_matching_files(local_dir, genre_pattern, report=report)
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
    _run_ssh(target, "mkdir -p " + " ".join(shlex.quote(d) for d in remote_dirs))

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
    """Remove one file whose path was returned by the remote find command."""
    _run_ssh(target, f"rm -f -- {shlex.quote(remote_path)}")


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
