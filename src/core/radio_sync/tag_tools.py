"""Tag reading/completion shared by the local app and the VPS.

This module must stay self-contained (stdlib + mutagen only): its source is
sent over ssh and executed by `python3` on the VPS, where `run_remote()` reads
a JSON payload {"dry_run": bool, "files": {remote_path: local_tags}} on stdin
and prints {"updated": {remote_path: [changed keys]}, "errors": {...}}.
"""

import json
import sys

# Keys exposed by mutagen's "easy" interfaces, plus the extra ones registered
# below for ID3 (EasyID3 lacks comment, musical key and producer).
_EXTRA_ID3_REGISTERED = False


def _register_extra_id3_keys():
    global _EXTRA_ID3_REGISTERED
    if _EXTRA_ID3_REGISTERED:
        return
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import COMM, TIPL

    EasyID3.RegisterTextKey("initialkey", "TKEY")

    # Only plain comments (empty description); tool frames like iTunNORM are kept.
    def comment_get(id3, key):
        return [text for frame in id3.getall("COMM") if not frame.desc for text in frame.text]

    def comment_set(id3, key, value):
        others = [frame for frame in id3.getall("COMM") if frame.desc]
        id3.setall("COMM", others + [COMM(encoding=3, lang="eng", desc="", text=value)])

    def comment_delete(id3, key):
        id3.setall("COMM", [frame for frame in id3.getall("COMM") if frame.desc])

    def producer_get(id3, key):
        frame = id3.get("TIPL")
        return [person for role, person in frame.people if role == "producer"] if frame else []

    def producer_set(id3, key, value):
        frame = id3.get("TIPL")
        others = [pair for pair in frame.people if pair[0] != "producer"] if frame else []
        id3.setall("TIPL", [TIPL(encoding=3, people=others + [["producer", v] for v in value])])

    def producer_delete(id3, key):
        producer_set(id3, key, [])

    EasyID3.RegisterKey("comment", comment_get, comment_set, comment_delete)
    EasyID3.RegisterKey("producer", producer_get, producer_set, producer_delete)
    _EXTRA_ID3_REGISTERED = True


def _open_easy(path):
    from mutagen import File as MutagenFile

    _register_extra_id3_keys()
    return MutagenFile(path, easy=True)


def _clean(values):
    if isinstance(values, str):
        values = [values]
    return [str(value) for value in values if str(value).strip()]


def read_tags(path):
    """Return {key: [values]} with non-empty values only ({} if unreadable)."""
    try:
        audio = _open_easy(path)
    except Exception:
        return {}
    if audio is None or not audio.tags:
        return {}
    tags = {}
    for key in list(audio.tags.keys()):
        try:
            values = _clean(audio.tags[key])
        except Exception:
            continue
        if values:
            tags[key] = values
    return tags


def update_tags(path, source_tags, dry_run=False):
    """Make non-empty source tag values authoritative; return changed keys."""
    audio = _open_easy(path)
    if audio is None:
        raise ValueError("unsupported audio file")
    if audio.tags is None:
        audio.add_tags()

    changed = []
    for key, values in source_tags.items():
        values = _clean(values)
        if not values:
            continue
        try:
            existing = _clean(audio.tags[key]) if key in audio.tags else []
        except Exception:
            existing = []
        if existing == values:
            continue
        try:
            audio.tags[key] = values
        except Exception:
            continue  # key not supported by this format / mutagen version
        changed.append(key)

    if changed and not dry_run:
        audio.save()
    return changed


def run_remote():
    payload = json.load(sys.stdin)
    result = {"updated": {}, "errors": {}}
    for path, source_tags in payload["files"].items():
        try:
            changed = update_tags(path, source_tags, dry_run=payload.get("dry_run", False))
            if changed:
                result["updated"][path] = changed
        except Exception as exc:
            result["errors"][path] = str(exc)
    json.dump(result, sys.stdout)
