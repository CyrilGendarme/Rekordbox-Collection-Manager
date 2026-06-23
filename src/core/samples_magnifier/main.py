import os
from pathlib import Path
from src.user_config import settings
from audio import (
    truncate_silence,
    read_audiosegment,
    normalize_audio_peak,
    write_audiosegment,
)
from src.services.audio_metadata_service import copy_mp3_metadata

SAMPLES_FOLDER = settings.SAMPLES_FOLDER
MODIFIED_SAMPLES_FOLDER = settings.MODIFIED_SAMPLES_FOLDER
AUDIO_FILES_EXTENSIOINS = settings.AUDIO_FILES_EXTENSIOINS
TRUNCATE_SILENCE_TRESHOLD = settings.TRUNCATE_SILENCE_TRESHOLD
TRUNCATE_SILENCE_CHUNK_SIZE = settings.TRUNCATE_SILENCE_CHUNK_SIZE
AUDIO_EXPORT_FORMAT = settings.AUDIO_EXPORT_FORMAT


def main():

    folder_path = Path(SAMPLES_FOLDER)  # Change to your target folder

    # Recursively find all audio files
    for audio_file in folder_path.rglob("*"):
        if audio_file.suffix.lower() in AUDIO_FILES_EXTENSIOINS:
            file_name = audio_file.stem
            extension = audio_file.suffix
            folder_abs_path = audio_file.parent.resolve()

            new_folder_abs_path = Path(
                str(folder_abs_path).replace(SAMPLES_FOLDER, MODIFIED_SAMPLES_FOLDER)
            )
            os.makedirs(new_folder_abs_path, exist_ok=True)

            new_file_name = f"{file_name.split('__')[-1]}"
            new_path = new_folder_abs_path / f"{new_file_name}{extension}"

            if not new_path.exists():
                audio = read_audiosegment(str(audio_file))
                normalized_audio = normalize_audio_peak(audio, target_peak_db=-1.0)
                truncated_audio = truncate_silence(
                    normalized_audio,
                    silence_threshold=TRUNCATE_SILENCE_TRESHOLD,
                    chunk_size=TRUNCATE_SILENCE_CHUNK_SIZE,
                )
                write_audiosegment(
                    audio=truncated_audio,
                    output_path=new_path,
                    format=AUDIO_EXPORT_FORMAT,
                    source_path=str(audio_file),
                )
                if audio_file.suffix.lower() == ".mp3" and new_path.suffix.lower() == ".mp3":
                    copy_mp3_metadata(
                        source_path=str(audio_file),
                        target_path=str(new_path),
                    )

            else:
                print(f"-------- new path already exists for: {new_path}")
           


if __name__ == "__main__":
    main()
