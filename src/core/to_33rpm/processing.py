from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import resample, resample_poly


SOURCE_RPM = 45.0
TARGET_RPM = 33.0
# Slower playback factor when a 45rpm record is played at 33rpm.
SLOWDOWN_FACTOR = SOURCE_RPM / TARGET_RPM


@dataclass(frozen=True)
class ProcessConfig:
    method: str = "polyphase"
    normalize: bool = True
    target_peak_dbfs: float = -1.0


def emulate_45_played_at_33(audio: np.ndarray, config: ProcessConfig) -> np.ndarray:
    """Return audio slowed/pitch-shifted like 45rpm played at 33rpm.

    Input shape may be (samples,) for mono or (samples, channels) for multichannel.
    """
    if audio.size == 0:
        return audio

    method = config.method.lower().strip()
    if method not in {"polyphase", "fft"}:
        raise ValueError("method must be 'polyphase' or 'fft'")

    # Keep processing in float64 to minimize cumulative rounding error.
    work = np.asarray(audio, dtype=np.float64)

    # Preserve channel layout while resampling the time axis.
    axis = 0
    if method == "polyphase":
        slowed = resample_poly(
            work,
            up=45,
            down=33,
            axis=axis,
            window=("kaiser", 8.6),
            padtype="line",
        )
    else:
        output_len = int(round(work.shape[axis] * SLOWDOWN_FACTOR))
        slowed = resample(work, num=output_len, axis=axis)

    if config.normalize:
        peak = float(np.max(np.abs(slowed)))
        if peak > 1.0:
            target_peak = 10.0 ** (config.target_peak_dbfs / 20.0)
            slowed = (slowed / peak) * target_peak

    return slowed.astype(np.float64, copy=False)
