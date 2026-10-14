"""Push music files whose genre matches a regex to a VPS over ssh/scp.

Only files missing on the VPS are transferred, to save bandwidth. Uploads go
to a temporary name and are renamed once complete, so a file present on the
VPS is always a full copy.

Files already on the VPS get their metadata completed from the local copy:
tags missing/empty remotely are filled in place on the VPS (only the tag
text travels, not the audio). Existing remote values are never overwritten.
This step needs `python3` with `mutagen` on the VPS
(e.g. `sudo apt install python3-mutagen`); without it, pushing still works.

Requires the system `ssh`/`scp` binaries and key-based authentication
(BatchMode is enabled, so password prompts fail instead of hanging).

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
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from src.core.radio_sync import tag_tools
from src.user_config import settings

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], None]

PARTIAL_SUFFIX = ".radiosync-part"


@dataclass(frozen=True)
class VpsTarget:
    host: str  # "user@host" or an alias from ~/.ssh/config
    remote_dir: str
    port: int = 22
    ssh_key: str = ""

    def ssh_options(self, port_flag: str) -> list[str]:
        options = [port_flag, str(self.port), "-o", "BatchMode=yes"]
        if self.ssh_key:
            options += ["-i", self.ssh_key]
        return options


@dataclass
class SyncResult:
    matched: int = 0
    skipped: int = 0
    pushed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    # relative path -> tag keys added (or that would be added on a dry run)
    metadata_updated: dict[str, list[str]] = field(default_factory=dict)
    metadata_failed: list[tuple[str, str]] = field(default_factory=list)


def find_matching_files(
    local_dir: Path,
    genre_pattern: str,
    extensions: tuple[str, ...] = settings.AUDIO_FILES_EXTENSIOINS,
) -> list[tuple[Path, dict[str, list[str]]]]:
    """Recursively list audio files whose genre matches, with their tags."""
    regex = re.compile(genre_pattern, re.IGNORECASE)
    lowered_extensions = tuple(ext.lower() for ext in extensions)
    matching = []
    for path in sorted(local_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in lowered_extensions:
            continue
        tags = tag_tools.read_tags(path)
        if regex.search(" / ".join(tags.get("genre", []))):
            matching.append((path, tags))
    return matching


def _run_ssh(target: VpsTarget, remote_command: str, stdin: str | None = None) -> str:
    completed = subprocess.run(
        ["ssh", *target.ssh_options("-p"), target.host, remote_command],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"ssh failed: {completed.stderr.strip()}")
    return completed.stdout


def list_remote_files(target: VpsTarget) -> set[str]:
    """Relative posix paths of the complete files under the remote dir."""
    remote_dir = shlex.quote(target.remote_dir)
    output = _run_ssh(
        target,
        f"mkdir -p {remote_dir} && "
        f"find {remote_dir} -type f ! -name '*{PARTIAL_SUFFIX}' -printf '%P\\n'",
    )
    return {line for line in output.splitlines() if line}


def _scp_uses_sftp() -> bool:
    """OpenSSH >= 9.0 scp uses SFTP: remote paths are not shell-expanded."""
    completed = subprocess.run(["ssh", "-V"], capture_output=True, text=True)
    match = re.search(r"OpenSSH\w*_(\d+)\.(\d+)", completed.stderr + completed.stdout)
    return bool(match) and (int(match.group(1)), int(match.group(2))) >= (9, 0)


def _scp_upload(target: VpsTarget, local_path: Path, remote_path: str, raw_remote: bool) -> None:
    """Upload to a temporary name, then rename so partial uploads never look complete."""
    partial_path = remote_path + PARTIAL_SUFFIX
    destination = partial_path if raw_remote else shlex.quote(partial_path)
    completed = subprocess.run(
        ["scp", *target.ssh_options("-P"), str(local_path), f"{target.host}:{destination}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "scp failed")
    _run_ssh(target, f"mv -f {shlex.quote(partial_path)} {shlex.quote(remote_path)}")


def complete_remote_metadata(
    target: VpsTarget,
    files: dict[str, dict[str, list[str]]],
    dry_run: bool = False,
) -> dict:
    """Fill tags missing on the VPS copies from local tags, in one ssh call.

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

    report(f"{result.skipped} already on VPS, {len(to_push)} to push.")

    if sync_metadata and already_remote:
        _sync_metadata(target, already_remote, dry_run, result, report)

    if dry_run:
        result.pushed = [relative for _, relative in to_push]
        return result
    if not to_push:
        return result

    remote_dirs = sorted(
        {posixpath.join(target.remote_dir, posixpath.dirname(rel)) for _, rel in to_push}
    )
    _run_ssh(target, "mkdir -p " + " ".join(shlex.quote(d) for d in remote_dirs))

    raw_remote = _scp_uses_sftp()
    for index, (local_path, relative) in enumerate(to_push, start=1):
        report(f"[{index}/{len(to_push)}] pushing {relative}")
        try:
            _scp_upload(
                target, local_path, posixpath.join(target.remote_dir, relative), raw_remote
            )
            result.pushed.append(relative)
        except Exception as exc:
            logger.error("Failed to push %s: %s", local_path, exc)
            result.failed.append((relative, str(exc)))

    report(
        f"Done: {len(result.pushed)} pushed, {result.skipped} skipped, "
        f"{len(result.failed)} failed, {len(result.metadata_updated)} metadata completed."
    )
    return result


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
        remote_result = complete_remote_metadata(
            target,
            {remote: already_remote[relative] for remote, relative in by_remote_path.items()},
            dry_run=dry_run,
        )
    except Exception as exc:
        report(f"Metadata sync skipped: {exc}")
        result.metadata_failed.append(("*", str(exc)))
        return

    verb = "would complete" if dry_run else "completed"
    for remote_path, keys in remote_result.get("updated", {}).items():
        relative = by_remote_path[remote_path]
        result.metadata_updated[relative] = keys
        report(f"{verb} metadata of {relative}: {', '.join(keys)}")
    for remote_path, error in remote_result.get("errors", {}).items():
        result.metadata_failed.append((by_remote_path[remote_path], error))
    report(f"Metadata: {len(result.metadata_updated)} remote file(s) {verb}.")


def target_from_settings() -> VpsTarget:
    return VpsTarget(
        host=settings.RADIO_VPS_HOST,
        remote_dir=settings.RADIO_VPS_REMOTE_DIR,
        port=settings.RADIO_VPS_PORT,
        ssh_key=settings.RADIO_VPS_SSH_KEY,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--local-dir", default=settings.RADIO_LOCAL_DIR)
    parser.add_argument("--host", default=settings.RADIO_VPS_HOST)
    parser.add_argument("--port", type=int, default=settings.RADIO_VPS_PORT)
    parser.add_argument("--remote-dir", default=settings.RADIO_VPS_REMOTE_DIR)
    parser.add_argument("--ssh-key", default=settings.RADIO_VPS_SSH_KEY)
    parser.add_argument("--genre-regex", default=settings.RADIO_GENRE_REGEX)
    parser.add_argument("--dry-run", action="store_true", help="List what would be pushed")
    parser.add_argument(
        "--no-metadata", action="store_true", help="Don't complete metadata on the VPS"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not args.host or not args.local_dir:
        parser.error("--host and --local-dir are required (or set RADIO_* in .env)")

    result = sync_to_vps(
        Path(args.local_dir),
        VpsTarget(args.host, args.remote_dir, args.port, args.ssh_key),
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


if __name__ == "__main__":
    main()
