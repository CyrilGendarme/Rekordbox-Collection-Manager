from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf


@dataclass(frozen=True)
class AudioMeta:
    sample_rate: int
    format: str | None
    subtype: str | None
    channels: int
    source_suffix: str


def read_audio(path: Path) -> tuple[np.ndarray, AudioMeta]:
    # Read in float64 to keep more headroom through DSP operations.
    audio, sr = sf.read(str(path), always_2d=False, dtype="float64")

    info = sf.info(str(path))
    channels = 1 if audio.ndim == 1 else audio.shape[1]
    meta = AudioMeta(
        sample_rate=sr,
        format=info.format,
        subtype=info.subtype,
        channels=channels,
        source_suffix=path.suffix.lower(),
    )
    return audio, meta


def _default_subtype_for_suffix(suffix: str) -> str | None:
    suffix = suffix.lower()
    if suffix in {".wav", ".flac", ".aif", ".aiff"}:
        return "PCM_24"
    return None


def write_audio(path: Path, audio: np.ndarray, meta: AudioMeta) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    out_suffix = path.suffix.lower()
    same_container = out_suffix == meta.source_suffix
    write_format = meta.format if same_container else None
    write_subtype = meta.subtype if same_container else _default_subtype_for_suffix(out_suffix)

    sf.write(
        file=str(path),
        data=audio,
        samplerate=meta.sample_rate,
        format=write_format,
        subtype=write_subtype,
    )
