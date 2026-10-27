from __future__ import annotations

import numpy as np

from src.core.to_33rpm.audio_enhancer.processing import (
    DynamicEQConfig,
    HighShelfConfig,
    LowPassConfig,
)
from src.core.to_33rpm.audio_enhancer.rendering import (
    EffectStageSpec,
    create_dynamic_eq_stream_processor,
    create_high_shelf_stream_processor,
    create_low_pass_stream_processor,
    process_array_in_parallel_effect_chain_stream,
)

EFFECT_CHAIN_STAGE_SPECS: dict[str, EffectStageSpec] = {
    "dynamic_eq": EffectStageSpec(
        processor_factory=create_dynamic_eq_stream_processor,
        config=DynamicEQConfig(center_hz=7200.0),
    ),
    "high_shelf": EffectStageSpec(
        processor_factory=create_high_shelf_stream_processor,
        config=HighShelfConfig(),
    ),
    "low_pass": EffectStageSpec(
        processor_factory=create_low_pass_stream_processor,
        config=LowPassConfig(),
    ),
}
EFFECT_CHAIN_ORDER: tuple[str, ...] = ("dynamic_eq", "high_shelf", "low_pass")


def apply_enhancer_chain(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    return process_array_in_parallel_effect_chain_stream(
        audio=audio,
        sample_rate=sample_rate,
        effect_stage_specs=EFFECT_CHAIN_STAGE_SPECS,
        effects=EFFECT_CHAIN_ORDER,
    )
