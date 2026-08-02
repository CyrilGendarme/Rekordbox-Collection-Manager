from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import lfilter

try:
    from numba import njit
except ImportError:  # pragma: no cover - optional dependency
    njit = None


if njit is not None:

    @njit(cache=True)
    def _dynamic_eq_kernel(
        work: np.ndarray,
        band: np.ndarray,
        envelope: np.ndarray,
        attack_coeff: float,
        release_coeff: float,
        threshold: float,
        max_cut_db: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        output = np.empty_like(work)
        env = envelope.copy()

        sample_count, channel_count = work.shape
        for sample_idx in range(sample_count):
            for channel_idx in range(channel_count):
                band_sample = band[sample_idx, channel_idx]
                level = abs(band_sample)

                coeff = attack_coeff if level > env[channel_idx] else release_coeff
                env[channel_idx] = (coeff * env[channel_idx]) + ((1.0 - coeff) * level)

                overshoot = (env[channel_idx] / threshold) - 1.0
                if overshoot < 0.0:
                    overshoot = 0.0

                reduction_ratio = overshoot / (1.0 + overshoot)
                reduction_db = max_cut_db * reduction_ratio
                gain = 10.0 ** (-reduction_db / 20.0)

                output[sample_idx, channel_idx] = work[sample_idx, channel_idx] - (
                    (1.0 - gain) * band_sample
                )

        return output, env

else:

    def _dynamic_eq_kernel(
        work: np.ndarray,
        band: np.ndarray,
        envelope: np.ndarray,
        attack_coeff: float,
        release_coeff: float,
        threshold: float,
        max_cut_db: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        output = np.empty_like(work)
        env = envelope.copy()

        for sample_idx in range(work.shape[0]):
            band_sample = band[sample_idx]
            level = np.abs(band_sample)
            rising = level > env
            coeff = np.where(rising, attack_coeff, release_coeff)
            env = (coeff * env) + ((1.0 - coeff) * level)

            overshoot = np.maximum((env / threshold) - 1.0, 0.0)
            reduction_ratio = overshoot / (1.0 + overshoot)
            reduction_db = max_cut_db * reduction_ratio
            gain = 10.0 ** (-reduction_db / 20.0)

            output[sample_idx] = work[sample_idx] - ((1.0 - gain) * band_sample)

        return output, env


@dataclass(frozen=True)
class LowPassConfig:
    cutoff_hz: float = 12_000.0
    q: float = 0.70710678118


@dataclass(frozen=True)
class HighShelfConfig:
    cutoff_hz: float = 9_000.0
    gain_db: float = -1.0
    slope: float = 1.0


@dataclass(frozen=True)
class DynamicEQConfig:
    center_hz: float = 7_200.0
    q: float = 1.2
    threshold_db: float = -16.0
    max_cut_db: float = 3.0
    attack_ms: float = 4.0
    release_ms: float = 90.0
    makeup_db: float = 0.0


@dataclass(frozen=True)
class DeEsserConfig:
    center_hz: float = 6_500.0
    q: float = 2.0
    threshold_db: float = -28.0
    max_reduction_db: float = 9.0
    attack_ms: float = 2.0
    release_ms: float = 120.0


def _db_to_linear(value_db: float) -> float:
    return float(10.0 ** (value_db / 20.0))


def _validate_frequency(sample_rate: int, frequency_hz: float) -> None:
    nyquist = sample_rate / 2.0
    if not 0.0 < frequency_hz < nyquist:
        raise ValueError(
            f"frequency_hz must be between 0 and Nyquist ({nyquist:.1f} Hz)"
        )


def _prepare_audio_block(audio: np.ndarray) -> tuple[np.ndarray, bool]:
    work = np.asarray(audio, dtype=np.float64)
    if work.ndim == 1:
        return work[:, None], True
    if work.ndim != 2:
        raise ValueError("audio must have shape (samples,) or (samples, channels)")
    return work, False


def _restore_audio_shape(audio: np.ndarray, squeeze_mono: bool) -> np.ndarray:
    if squeeze_mono and audio.shape[1] == 1:
        return audio[:, 0]
    return audio


class AudioEffect:
    def process_block(self, audio: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def process(self, audio: np.ndarray) -> np.ndarray:
        return self.process_block(audio)

    def reset(self) -> None:
        return None


class EffectChain(AudioEffect):
    def __init__(self, *effects: AudioEffect) -> None:
        self.effects = list(effects)

    def process_block(self, audio: np.ndarray) -> np.ndarray:
        processed = np.asarray(audio, dtype=np.float64)
        for effect in self.effects:
            processed = effect.process_block(processed)
        return processed

    def reset(self) -> None:
        for effect in self.effects:
            effect.reset()


class _BiquadFilter:
    def __init__(self, b: np.ndarray, a: np.ndarray) -> None:
        self.b = np.asarray(b, dtype=np.float64)
        self.a = np.asarray(a, dtype=np.float64)
        self._zi: np.ndarray | None = None

    def reset(self) -> None:
        self._zi = None

    def _ensure_state(self, channels: int) -> None:
        order = max(self.a.size, self.b.size) - 1
        if self._zi is None or self._zi.shape != (order, channels):
            self._zi = np.zeros((order, channels), dtype=np.float64)

    def process_block(self, audio: np.ndarray) -> np.ndarray:
        work, squeeze_mono = _prepare_audio_block(audio)
        if work.size == 0:
            return _restore_audio_shape(work.copy(), squeeze_mono)

        self._ensure_state(work.shape[1])
        assert self._zi is not None

        out, zi = lfilter(self.b, self.a, work, axis=0, zi=self._zi)
        self._zi = zi
        return _restore_audio_shape(out, squeeze_mono)


def _normalize_biquad_coefficients(
    b0: float,
    b1: float,
    b2: float,
    a0: float,
    a1: float,
    a2: float,
) -> tuple[np.ndarray, np.ndarray]:
    b = np.array([b0 / a0, b1 / a0, b2 / a0], dtype=np.float64)
    a = np.array([1.0, a1 / a0, a2 / a0], dtype=np.float64)
    return b, a


def _low_pass_coefficients(
    sample_rate: int, cutoff_hz: float, q: float
) -> tuple[np.ndarray, np.ndarray]:
    _validate_frequency(sample_rate, cutoff_hz)
    if q <= 0.0:
        raise ValueError("q must be positive")

    omega = 2.0 * np.pi * cutoff_hz / sample_rate
    sin_omega = np.sin(omega)
    cos_omega = np.cos(omega)
    alpha = sin_omega / (2.0 * q)

    return _normalize_biquad_coefficients(
        (1.0 - cos_omega) / 2.0,
        1.0 - cos_omega,
        (1.0 - cos_omega) / 2.0,
        1.0 + alpha,
        -2.0 * cos_omega,
        1.0 - alpha,
    )


def _band_pass_coefficients(
    sample_rate: int, center_hz: float, q: float
) -> tuple[np.ndarray, np.ndarray]:
    _validate_frequency(sample_rate, center_hz)
    if q <= 0.0:
        raise ValueError("q must be positive")

    omega = 2.0 * np.pi * center_hz / sample_rate
    sin_omega = np.sin(omega)
    cos_omega = np.cos(omega)
    alpha = sin_omega / (2.0 * q)

    return _normalize_biquad_coefficients(
        alpha,
        0.0,
        -alpha,
        1.0 + alpha,
        -2.0 * cos_omega,
        1.0 - alpha,
    )


def _high_shelf_coefficients(
    sample_rate: int,
    cutoff_hz: float,
    gain_db: float,
    slope: float,
) -> tuple[np.ndarray, np.ndarray]:
    _validate_frequency(sample_rate, cutoff_hz)
    if slope <= 0.0:
        raise ValueError("slope must be positive")

    omega = 2.0 * np.pi * cutoff_hz / sample_rate
    sin_omega = np.sin(omega)
    cos_omega = np.cos(omega)
    amplitude = 10.0 ** (gain_db / 40.0)
    alpha = (
        sin_omega
        / 2.0
        * np.sqrt((amplitude + (1.0 / amplitude)) * ((1.0 / slope) - 1.0) + 2.0)
    )
    beta = 2.0 * np.sqrt(amplitude) * alpha

    return _normalize_biquad_coefficients(
        amplitude * ((amplitude + 1.0) + ((amplitude - 1.0) * cos_omega) + beta),
        -2.0 * amplitude * ((amplitude - 1.0) + ((amplitude + 1.0) * cos_omega)),
        amplitude * ((amplitude + 1.0) + ((amplitude - 1.0) * cos_omega) - beta),
        (amplitude + 1.0) - ((amplitude - 1.0) * cos_omega) + beta,
        2.0 * ((amplitude - 1.0) - ((amplitude + 1.0) * cos_omega)),
        (amplitude + 1.0) - ((amplitude - 1.0) * cos_omega) - beta,
    )


class BiquadEffect(AudioEffect):
    def __init__(self, b: np.ndarray, a: np.ndarray) -> None:
        self._filter = _BiquadFilter(b, a)

    def process_block(self, audio: np.ndarray) -> np.ndarray:
        return self._filter.process_block(audio)

    def reset(self) -> None:
        self._filter.reset()


class DynamicEQEffect(AudioEffect):
    def __init__(
        self,
        sample_rate: int,
        center_hz: float,
        q: float,
        threshold_db: float,
        max_cut_db: float,
        attack_ms: float,
        release_ms: float,
        makeup_db: float = 0.0,
    ) -> None:
        if max_cut_db < 0.0:
            raise ValueError("max_cut_db must be non-negative")
        if attack_ms <= 0.0 or release_ms <= 0.0:
            raise ValueError("attack_ms and release_ms must be positive")

        b, a = _band_pass_coefficients(sample_rate, center_hz, q)
        self._band_detector = _BiquadFilter(b, a)
        self._sample_rate = sample_rate
        self._threshold = _db_to_linear(threshold_db)
        self._max_cut_db = max_cut_db
        self._makeup_gain = _db_to_linear(makeup_db)
        self._attack_coeff = np.exp(-1.0 / (sample_rate * (attack_ms / 1_000.0)))
        self._release_coeff = np.exp(-1.0 / (sample_rate * (release_ms / 1_000.0)))
        self._envelope: np.ndarray | None = None

    def reset(self) -> None:
        self._band_detector.reset()
        self._envelope = None

    def _ensure_state(self, channels: int) -> None:
        if self._envelope is None or self._envelope.shape[0] != channels:
            self._envelope = np.zeros(channels, dtype=np.float64)

    def process_block(self, audio: np.ndarray) -> np.ndarray:
        work, squeeze_mono = _prepare_audio_block(audio)
        if work.size == 0:
            return _restore_audio_shape(work.copy(), squeeze_mono)

        band = _prepare_audio_block(self._band_detector.process_block(work))[0]
        self._ensure_state(work.shape[1])
        assert self._envelope is not None

        output, envelope = _dynamic_eq_kernel(
            work,
            band,
            self._envelope,
            self._attack_coeff,
            self._release_coeff,
            self._threshold,
            self._max_cut_db,
        )
        self._envelope = envelope

        if self._makeup_gain != 1.0:
            output *= self._makeup_gain

        return _restore_audio_shape(output, squeeze_mono)


def create_low_pass_processor(
    sample_rate: int, config: LowPassConfig | None = None
) -> AudioEffect:
    config = config or LowPassConfig()
    b, a = _low_pass_coefficients(sample_rate, config.cutoff_hz, config.q)
    return BiquadEffect(b, a)


def create_dynamic_eq_processor(
    sample_rate: int, config: DynamicEQConfig | None = None
) -> AudioEffect:
    config = config or DynamicEQConfig()
    return DynamicEQEffect(
        sample_rate=sample_rate,
        center_hz=config.center_hz,
        q=config.q,
        threshold_db=config.threshold_db,
        max_cut_db=config.max_cut_db,
        attack_ms=config.attack_ms,
        release_ms=config.release_ms,
        makeup_db=config.makeup_db,
    )


def create_de_esser_processor(
    sample_rate: int, config: DeEsserConfig | None = None
) -> AudioEffect:
    config = config or DeEsserConfig()
    return DynamicEQEffect(
        sample_rate=sample_rate,
        center_hz=config.center_hz,
        q=config.q,
        threshold_db=config.threshold_db,
        max_cut_db=config.max_reduction_db,
        attack_ms=config.attack_ms,
        release_ms=config.release_ms,
    )


def create_high_shelf_processor(
    sample_rate: int, config: HighShelfConfig | None = None
) -> AudioEffect:
    config = config or HighShelfConfig()
    b, a = _high_shelf_coefficients(
        sample_rate, config.cutoff_hz, config.gain_db, config.slope
    )
    return BiquadEffect(b, a)


def apply_low_pass(
    audio: np.ndarray,
    sample_rate: int,
    config: LowPassConfig | None = None,
) -> np.ndarray:
    return create_low_pass_processor(sample_rate, config).process(audio)


def apply_dynamic_eq(
    audio: np.ndarray,
    sample_rate: int,
    config: DynamicEQConfig | None = None,
) -> np.ndarray:
    return create_dynamic_eq_processor(sample_rate, config).process(audio)


def apply_de_esser(
    audio: np.ndarray,
    sample_rate: int,
    config: DeEsserConfig | None = None,
) -> np.ndarray:
    return create_de_esser_processor(sample_rate, config).process(audio)


def apply_high_shelf(
    audio: np.ndarray,
    sample_rate: int,
    config: HighShelfConfig | None = None,
) -> np.ndarray:
    return create_high_shelf_processor(sample_rate, config).process(audio)
