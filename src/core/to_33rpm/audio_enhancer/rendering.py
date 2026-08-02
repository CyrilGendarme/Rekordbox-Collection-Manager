from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from queue import Empty, Queue
import threading
import time
from typing import Any, Callable

import numpy as np

from src.core.to_33rpm.audio_enhancer.io_audio import read_audio, write_audio
from src.core.to_33rpm.audio_enhancer.processing import (
    AudioEffect,
    DeEsserConfig,
    DynamicEQConfig,
    EffectChain,
    HighShelfConfig,
    LowPassConfig,
    apply_de_esser,
    apply_dynamic_eq,
    apply_high_shelf,
    apply_low_pass,
    create_de_esser_processor,
    create_dynamic_eq_processor,
    create_high_shelf_processor,
    create_low_pass_processor,
)

def _render_effect_to_file(
    input_path: Path,
    output_path: Path,
    processor_factory,
) -> Path:
    started = time.perf_counter()
    audio, meta = read_audio(input_path)
    processed = processor_factory(audio, meta.sample_rate)
    write_audio(output_path, processed, meta)
    elapsed = time.perf_counter() - started
    print(f"Rendered {output_path.name} in {elapsed:.2f}s")
    return output_path


def render_low_pass_track(
    input_path: Path,
    output_path: Path,
    config: LowPassConfig | None = None,
) -> Path:
    return _render_effect_to_file(
        input_path,
        output_path,
        lambda audio, sample_rate: apply_low_pass(audio, sample_rate, config),
    )


def render_dynamic_eq_track(
    input_path: Path,
    output_path: Path,
    config: DynamicEQConfig | None = None,
) -> Path:
    return _render_effect_to_file(
        input_path,
        output_path,
        lambda audio, sample_rate: apply_dynamic_eq(audio, sample_rate, config),
    )


def render_de_esser_track(
    input_path: Path,
    output_path: Path,
    config: DeEsserConfig | None = None,
) -> Path:
    return _render_effect_to_file(
        input_path,
        output_path,
        lambda audio, sample_rate: apply_de_esser(audio, sample_rate, config),
    )


def render_high_shelf_track(
    input_path: Path,
    output_path: Path,
    config: HighShelfConfig | None = None,
) -> Path:
    return _render_effect_to_file(
        input_path,
        output_path,
        lambda audio, sample_rate: apply_high_shelf(audio, sample_rate, config),
    )


def create_low_pass_stream_processor(
    sample_rate: int,
    config: LowPassConfig | None = None,
) -> AudioEffect:
    return create_low_pass_processor(sample_rate, config)


def create_dynamic_eq_stream_processor(
    sample_rate: int,
    config: DynamicEQConfig | None = None,
) -> AudioEffect:
    return create_dynamic_eq_processor(sample_rate, config)


def create_de_esser_stream_processor(
    sample_rate: int,
    config: DeEsserConfig | None = None,
) -> AudioEffect:
    return create_de_esser_processor(sample_rate, config)


def create_high_shelf_stream_processor(
    sample_rate: int,
    config: HighShelfConfig | None = None,
) -> AudioEffect:
    return create_high_shelf_processor(sample_rate, config)


def process_stream_chunk(effect: AudioEffect, input_chunk: np.ndarray) -> np.ndarray:
    return effect.process_block(input_chunk)




def process_array_in_stream(
    effect: AudioEffect,
    audio: np.ndarray,
    block_size: int = 256,
) -> np.ndarray:
    '''
    block_size = 256 for a good balance (usually stable, low enough latency)
    Try 128 if you want lower latency and your CPU/audio driver is solid
    Move to 512 if you hear crackles/dropouts
    
    block duration reference at 48 kHz:
    128 samples: 2.67 ms
    256 samples: 5.33 ms
    512 samples: 10.67 ms
    '''
    
    if block_size <= 0:
        raise ValueError("block_size must be positive")

    if audio.shape[0] == 0:
        return audio.copy()

    processed = np.empty_like(audio)
    total_samples = audio.shape[0]
    for start in range(0, total_samples, block_size):
        end = min(start + block_size, total_samples)
        processed[start:end] = process_stream_chunk(effect, audio[start:end])
    return processed


def process_array_in_parallel_effect_chain_stream(
    audio: np.ndarray,
    sample_rate: int,
    effect_stage_specs: dict[str, EffectStageSpec],
    effects: tuple[str, ...],
    block_size: int = 65_536,
    queue_size: int = 4,
) -> np.ndarray:
    if block_size <= 0:
        raise ValueError("block_size must be positive")
    if queue_size <= 0:
        raise ValueError("queue_size must be positive")

    if len(effects) == 0:
        return audio.copy()
    if audio.shape[0] == 0:
        return audio.copy()

    processed = np.empty_like(audio)
    block_ranges: list[tuple[int, int]] = []
    for start in range(0, audio.shape[0], block_size):
        end = min(start + block_size, audio.shape[0])
        block_ranges.append((start, end))

    queues: list[Queue] = [Queue(maxsize=queue_size) for _ in range(len(effects) + 1)]
    sentinel = object()
    error_queue: Queue = Queue()

    def _stage_worker(effect_name: str, in_queue: Queue, out_queue: Queue) -> None:
        try:
            stage = effect_stage_specs[effect_name]
            print(f"[CHAIN] START: {effect_name}")
            stage_started = time.perf_counter()

            effect = stage.processor_factory(sample_rate, stage.config)
            while True:
                item = in_queue.get()
                if item is sentinel:
                    out_queue.put(sentinel)
                    break

                block_index, block = item
                out_block = process_stream_chunk(effect, block)
                out_queue.put((block_index, out_block))

            stage_elapsed = time.perf_counter() - stage_started
            print(f"[CHAIN] DONE: {effect_name} ({stage_elapsed:.2f}s)")
        except Exception as exc:  # pragma: no cover - defensive propagation path
            error_queue.put((effect_name, exc))
            out_queue.put(sentinel)

    workers: list[threading.Thread] = []
    for index, effect_name in enumerate(effects):
        worker = threading.Thread(
            target=_stage_worker,
            args=(effect_name, queues[index], queues[index + 1]),
            daemon=False,
        )
        workers.append(worker)
        worker.start()

    def _feed_input_blocks() -> None:
        try:
            for block_index, (start, end) in enumerate(block_ranges):
                queues[0].put((block_index, audio[start:end]))
            queues[0].put(sentinel)
        except Exception as exc:  # pragma: no cover - defensive propagation path
            error_queue.put(("input_feeder", exc))
            queues[0].put(sentinel)

    feeder = threading.Thread(target=_feed_input_blocks, daemon=False)
    feeder.start()

    blocks_written = 0
    while blocks_written < len(block_ranges):
        if not error_queue.empty():
            effect_name, exc = error_queue.get()
            raise RuntimeError(f"Pipeline stage '{effect_name}' failed") from exc

        try:
            item = queues[-1].get(timeout=1.0)
        except Empty:
            alive = any(worker.is_alive() for worker in workers)
            if not alive:
                if not error_queue.empty():
                    effect_name, exc = error_queue.get()
                    raise RuntimeError(f"Pipeline stage '{effect_name}' failed") from exc
                raise RuntimeError("Parallel chain pipeline stopped before producing all blocks")
            continue

        if item is sentinel:
            if blocks_written < len(block_ranges):
                raise RuntimeError("Parallel chain pipeline terminated early")
            break

        block_index, out_block = item
        start, end = block_ranges[block_index]
        processed[start:end] = out_block
        blocks_written += 1

    for worker in workers:
        worker.join(timeout=2.0)
        if worker.is_alive():
            raise RuntimeError("Parallel chain pipeline did not shut down cleanly")

    feeder.join(timeout=2.0)
    if feeder.is_alive():
        raise RuntimeError("Input feeder did not shut down cleanly")

    if not error_queue.empty():
        effect_name, exc = error_queue.get()
        raise RuntimeError(f"Pipeline stage '{effect_name}' failed") from exc

    return processed


@dataclass(frozen=True)
class EffectRenderSpec:
    renderer: Callable[..., Path]
    output_path: Path
    config: Any = None


@dataclass(frozen=True)
class EffectStageSpec:
    processor_factory: Callable[..., AudioEffect]
    config: Any = None


def render_all_reference_outputs(
    input_path: Path,
    effect_renderers: dict[str, EffectRenderSpec],
    effects: tuple[str, ...] = ("low_pass",),
) -> list[Path]:
    outputs: list[Path] = []
    for effect_name in effects:
        spec = effect_renderers[effect_name]
        outputs.append(
            spec.renderer(
                input_path=input_path,
                output_path=spec.output_path,
                config=spec.config,
            )
        )
    return outputs


def create_stream_effect_processor(
    sample_rate: int,
    effect_name: str,
    effect_stage_specs: dict[str, EffectStageSpec],
) -> AudioEffect:
    stage = effect_stage_specs[effect_name]
    return stage.processor_factory(sample_rate, stage.config)


def create_effect_chain_stream_processor(
    sample_rate: int,
    effect_stage_specs: dict[str, EffectStageSpec],
    effects: tuple[str, ...] = ("dynamic_eq 3", "high_shelf", "low_pass"),
) -> AudioEffect:
    processors: list[AudioEffect] = []
    for effect_name in effects:
        stage = effect_stage_specs[effect_name]
        processors.append(stage.processor_factory(sample_rate, stage.config))
    return EffectChain(*processors)


def render_effect_chain(
    input_path: Path,
    output_path: Path,
    effect_stage_specs: dict[str, EffectStageSpec],
    effects: tuple[str, ...] = ("dynamic_eq 3", "high_shelf", "low_pass"),
    block_size: int = 65_536,
    parallel_pipeline: bool = True,
) -> Path:
    started = time.perf_counter()
    audio, meta = read_audio(input_path)

    if parallel_pipeline and len(effects) > 1:
        processed = process_array_in_parallel_effect_chain_stream(
            audio=audio,
            sample_rate=meta.sample_rate,
            effect_stage_specs=effect_stage_specs,
            effects=effects,
            block_size=block_size,
        )
    else:
        processed = audio
        for effect_name in effects:
            stage = effect_stage_specs[effect_name]
            print(f"[CHAIN] START: {effect_name}")
            effect_started = time.perf_counter()

            effect = stage.processor_factory(meta.sample_rate, stage.config)
            processed = process_array_in_stream(effect, processed, block_size=block_size)

            effect_elapsed = time.perf_counter() - effect_started
            print(f"[CHAIN] DONE: {effect_name} ({effect_elapsed:.2f}s)")

    write_audio(output_path, processed, meta)
    elapsed = time.perf_counter() - started
    print(
        f"Rendered chain [{', '.join(effects)}] to {output_path.name} in {elapsed:.2f}s"
    )
    return output_path
