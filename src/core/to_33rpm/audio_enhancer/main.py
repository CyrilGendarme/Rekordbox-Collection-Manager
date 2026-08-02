from pathlib import Path

from src.core.to_33rpm.audio_enhancer.processing import DeEsserConfig, DynamicEQConfig, HighShelfConfig, LowPassConfig
from src.core.to_33rpm.audio_enhancer.rendering import (
    EffectRenderSpec,
    EffectStageSpec,
    create_de_esser_stream_processor,
    create_dynamic_eq_stream_processor,
    create_high_shelf_stream_processor,
    create_low_pass_stream_processor,
    render_de_esser_track,
    render_dynamic_eq_track,
    render_effect_chain,
    render_high_shelf_track,
    render_low_pass_track,
)


INPUT_PATH = Path("C:\\Users\\User\\Desktop\\musique\\tracks\\33 rpm\\test in.wav")
OUTPUT_PATH_LOW_PASS = Path(
    "C:\\Users\\User\\Desktop\\musique\\tracks\\33 rpm\\test low pass.wav"
)
OUTPUT_PATH_DYNAMIC_EQ_1 = Path(
    "C:\\Users\\User\\Desktop\\musique\\tracks\\33 rpm\\test dynamic eq 1.wav"
)
OUTPUT_PATH_DYNAMIC_EQ_2 = Path(
    "C:\\Users\\User\\Desktop\\musique\\tracks\\33 rpm\\test dynamic eq 2.wav"
)
OUTPUT_PATH_DYNAMIC_EQ_3 = Path(
    "C:\\Users\\User\\Desktop\\musique\\tracks\\33 rpm\\test dynamic eq 3.wav"
)
OUTPUT_PATH_DE_ESSER = Path(
    "C:\\Users\\User\\Desktop\\musique\\tracks\\33 rpm\\test de-esser.wav"
)
OUTPUT_PATH_HIGH_SHELF = Path(
    "C:\\Users\\User\\Desktop\\musique\\tracks\\33 rpm\\test high shelf.wav"
)
OUTPUT_PATH_CHAIN = Path(
    "C:\\Users\\User\\Desktop\\musique\\tracks\\33 rpm\\test chain.wav"
)


EFFECT_RENDERERS: dict[str, EffectRenderSpec] = {
    "dynamic_eq 1": EffectRenderSpec(
        renderer=render_dynamic_eq_track,
        output_path=OUTPUT_PATH_DYNAMIC_EQ_1,
        config=DynamicEQConfig(center_hz=4_800.0),
    ),
    "dynamic_eq 2": EffectRenderSpec(
        renderer=render_dynamic_eq_track,
        output_path=OUTPUT_PATH_DYNAMIC_EQ_2,
        config=DynamicEQConfig(center_hz=6000.0),
    ),
    "dynamic_eq 3": EffectRenderSpec(
        renderer=render_dynamic_eq_track,
        output_path=OUTPUT_PATH_DYNAMIC_EQ_3,
        config=DynamicEQConfig(center_hz=7200.0),
    ),
    "high_shelf": EffectRenderSpec(
        renderer=render_high_shelf_track,
        output_path=OUTPUT_PATH_HIGH_SHELF,
        config=HighShelfConfig(),
    ),
    "low_pass": EffectRenderSpec(
        renderer=render_low_pass_track,
        output_path=OUTPUT_PATH_LOW_PASS,
        config=LowPassConfig(),
    ),
    "de_esser": EffectRenderSpec(
        renderer=render_de_esser_track,
        output_path=OUTPUT_PATH_DE_ESSER,
        config=DeEsserConfig(),
    ),
}


EFFECT_STAGE_SPECS: dict[str, EffectStageSpec] = {
    "dynamic_eq 1": EffectStageSpec(
        processor_factory=create_dynamic_eq_stream_processor,
        config=DynamicEQConfig(center_hz=4_800.0),
    ),
    "dynamic_eq 2": EffectStageSpec(
        processor_factory=create_dynamic_eq_stream_processor,
        config=DynamicEQConfig(center_hz=6000.0),
    ),
    "dynamic_eq 3": EffectStageSpec(
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
    "de_esser": EffectStageSpec(
        processor_factory=create_de_esser_stream_processor,
        config=DeEsserConfig(),
    ),
}


def run_default() -> Path:
    chain_effects = ("dynamic_eq 3", "high_shelf", "low_pass")
    output_path = render_effect_chain(
        input_path=INPUT_PATH,
        output_path=OUTPUT_PATH_CHAIN,
        effect_stage_specs=EFFECT_STAGE_SPECS,
        effects=chain_effects,
    )
    print(f"Done: {output_path}")
    return output_path


if __name__ == "__main__":
    run_default()
