from pathlib import Path

from src.core.to_33rpm.io_audio import read_audio, write_audio
from src.core.to_33rpm.processing import ProcessConfig, emulate_45_played_at_33


INPUT_PATH = Path("C:\\Users\\User\\Desktop\\temp2\\test\\Retromigration x Niklas Wandt - A1. Retromigration x Niklas Wandt - New Days.mp3")
OUTPUT_PATH = Path("C:\\Users\\User\\Desktop\\temp2\\test\\33rpm\\testeur.mp3")

LOSSY_SUFFIXES = {".mp3", ".ogg", ".opus", ".m4a", ".aac", ".wma"}


def main() -> int:
    if not INPUT_PATH.exists():
        print(f"Input file not found: {INPUT_PATH}")
        return 1

    audio, meta = read_audio(INPUT_PATH)

    if INPUT_PATH.suffix.lower() in LOSSY_SUFFIXES:
        print("Warning: input is lossy; it already contains codec losses.")

    if OUTPUT_PATH.suffix.lower() in LOSSY_SUFFIXES:
        print("Warning: output is lossy; re-encoding will add generation loss.")

    processed = emulate_45_played_at_33(
        audio,
        ProcessConfig(method="polyphase", normalize=True, target_peak_dbfs=-1.0),
    )
    write_audio(OUTPUT_PATH, processed, meta)

    print(f"Done: {INPUT_PATH} -> {OUTPUT_PATH}")
    print(f"Input format/subtype: {meta.format}/{meta.subtype}")
    print(f"Output extension: {OUTPUT_PATH.suffix.lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
