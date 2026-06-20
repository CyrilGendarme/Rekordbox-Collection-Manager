import re
    
def standardize_name(raw: str) -> tuple[str, str, str]:
    """
    Derive (track_name, artist, album) from a raw Rekordbox filename/title.

    Rules applied in order:
    1. Extract a label/catalog tag like ``(AB123)`` or ``[AB123]`` -> album;
       remove it from the working string.
    2. Remove every character that is not alphanumeric, space, hyphen,
       underscore or slash; collapse multiple spaces; strip.
    3. Any word whose every letter is upper-case (e.g. "ACDC", "DJ") is
       title-cased: first letter kept, rest lowered.
    4. If the string contains " - ": part before is artist, part after is
       track name.
    """
    s = raw

    # Rule 1 — extract special regex
    str_to_remove = ["(Official Video)", "(Audio)", "(Video Clip)", "(Clip Officiel)"]

    pattern = re.compile(
        "|".join(re.escape(x) for x in str_to_remove), flags=re.IGNORECASE
    )

    s = pattern.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()

    # Rule 2 — extract label code e.g. (WL001) or [ABC12]
    album = ""
    label_re = re.compile(r"[\(\[]\s*([A-Z]+\d+)\s*[\)\]]")
    m = label_re.search(s)
    if m:
        album = m.group(1)
        s = (s[: m.start()] + s[m.end() :]).strip()

    # Rule 3 — strip non-allowed characters then collapse spaces
    s = re.sub(r"[^\w \-_/()\[\]&]", "", s)
    s = re.sub(r" +", " ", s).strip()

    # Rule 3 — title-case fully upper-case words (2+ chars)
    def _fix_word(w: str) -> str:
        if len(w) > 1 and w.isupper():
            return w[0] + w[1:].lower()
        return w

    s = " ".join(_fix_word(w) for w in s.split(" ") if w)

    # Rule 4 — "Artist - Track" split
    artist = ""
    if " - " in s:
        artist, _, s = s.partition(" - ")
        artist = artist.strip()
        s = s.strip()

    return s, artist, album
