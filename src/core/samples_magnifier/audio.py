from pydub import AudioSegment
from pydub.utils import mediainfo
from pydub.silence import detect_nonsilent
import re

from src.user_config import settings

DURATION_BETWEEN_TTS_SEGMENT = settings.DURATION_BETWEEN_TTS_SEGMENT
DURATION_BETWEEN_MAIN_SEQUENCES = settings.DURATION_BETWEEN_MAIN_SEQUENCES


def normalize_audio_peak(
    audio: AudioSegment,
    target_peak_db: float = -1.0,
) -> AudioSegment:
    """
    Normalizes audio to a target peak dBFS (Audacity-style normalization).

    Equivalent to:
    Audacity → Effect → Normalize → Peak amplitude = -1.0 dB

    Args:
        audio (AudioSegment): Input audio
        target_peak_db (float): Target peak level in dBFS (default: -1.0)

    Returns:
        AudioSegment: Peak-normalized audio
    """

    # Current peak level in dBFS (max sample)
    current_peak_db = audio.max_dBFS

    # If audio is completely silent
    if current_peak_db == float("-inf"):
        return audio

    # Gain needed to reach target peak
    gain_db = target_peak_db - current_peak_db

    return audio.apply_gain(gain_db)


def truncate_silence(
    audio: AudioSegment,
    silence_threshold=-40.0,
    chunk_size=10,
    export_format="mp3",
    output_path: str | None = None,
    source_path: str | None = None,
):
    """
    Removes silence from the end of the audio.
    - `silence_threshold`: Threshold below which the audio is considered silent (in dBFS).
    - `chunk_size`: Size of the chunks to evaluate silence.
    """

    non_silent_ranges = detect_nonsilent(
        audio, min_silence_len=chunk_size, silence_thresh=silence_threshold
    )
    if not non_silent_ranges:
        return audio

    # Get the range of non-silent audio
    start, end = non_silent_ranges[0][0], non_silent_ranges[-1][1]
    truncated_audio = audio[start:end]

    if output_path is not None:
        export_kwargs = {}
        if export_format.lower() == "mp3":
            export_kwargs = _get_mp3_export_kwargs(source_path=source_path)
        truncated_audio.export(output_path, format=export_format, **export_kwargs)

    return truncated_audio


def write_audiosegment(
    audio: AudioSegment,
    output_path: str,
    format: str = "mp3",
    source_path: str | None = None,
) -> None:
    export_kwargs = {}
    if format.lower() == "mp3":
        export_kwargs = _get_mp3_export_kwargs(source_path=source_path)
    audio.export(output_path, format=format, **export_kwargs)


def _get_mp3_export_kwargs(source_path: str | None = None) -> dict:
    """
    Build ffmpeg export kwargs that keep MP3 output close to source quality.

    - For CBR/ABR sources: preserve source kbps.
    - For VBR sources: preserve source quantization when detectable, otherwise
      use a high-quality VBR fallback.
    """
    if not source_path:
        return {}

    try:
        info = mediainfo(source_path)
    except Exception:
        return {}

    bit_rate_mode = (info.get("bit_rate_mode") or "").upper()

    # Prefer preserving VBR quantization if source encoder settings expose it.
    if bit_rate_mode == "VBR":
        encoder_settings = (
            info.get("TAG:encoder_settings")
            or info.get("encoder_settings")
            or info.get("TAG:encoder")
            or ""
        )
        match = re.search(r"-V\s*([0-9](?:\.[0-9])?)", encoder_settings)
        if match:
            return {"parameters": ["-q:a", match.group(1)]}
        return {"parameters": ["-q:a", "2"]}

    # For non-VBR sources, keep the source bitrate when available.
    bit_rate = info.get("bit_rate") or info.get("overall_bit_rate")
    if bit_rate and str(bit_rate).isdigit():
        kbps = max(8, int(round(int(bit_rate) / 1000)))
        return {"bitrate": f"{kbps}k"}

    return {}


def read_audiosegment(input_path: str, from_mp3: bool = False) -> AudioSegment:
    if from_mp3:
        audio = AudioSegment.from_mp3(input_path)
    else:
        audio = AudioSegment.from_file(input_path)
    return audio
