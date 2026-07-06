#!/usr/bin/env python3
"""Runs WhisperX in a separate process so a native crash, hang, or
out-of-memory inside torch/ctranslate2 can never take down the GUI app.

Usage: whisperx_runner.py <audio> <out_json>
Config via env: WHISPERX_MODEL / WHISPER_MODEL, WHISPER_DEVICE,
WHISPER_COMPUTE, WHISPERX_BATCH, WHISPERX_VAD, WHISPERX_MODEL_DIR.
Writes {"language", "segments": [{"start", "end", "text", "words": [...]}]}.
"""

import json
import os
import sys
import warnings
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent


def prepare_environment() -> None:
    av_libs = APP_ROOT / ".venv" / "Lib" / "site-packages" / "av.libs"
    if hasattr(os, "add_dll_directory") and av_libs.exists():
        try:
            os.add_dll_directory(str(av_libs))
        except OSError:
            pass
    nltk_data = APP_ROOT / ".venv" / "nltk_data"
    if nltk_data.exists():
        os.environ.setdefault("NLTK_DATA", str(nltk_data))
    warnings.filterwarnings(
        "ignore",
        message=r"(?s).*torchcodec is not installed correctly.*",
        category=UserWarning,
    )


def main() -> int:
    audio_path, out_path = sys.argv[1:3]
    prepare_environment()

    import whisperx

    device = os.getenv("WHISPER_DEVICE", "cpu")
    compute_type = os.getenv("WHISPER_COMPUTE", "int8")
    model_name = os.getenv("WHISPERX_MODEL", os.getenv("WHISPER_MODEL", "base"))
    batch_size = max(1, int(os.getenv("WHISPERX_BATCH", "4")))
    vad_method = os.getenv("WHISPERX_VAD", os.getenv("WHISPERX_VAD_METHOD", "silero"))
    model_dir = Path(os.getenv("WHISPERX_MODEL_DIR", str(APP_ROOT / "work" / "whisperx_models")))
    if not model_dir.is_absolute():
        model_dir = APP_ROOT / model_dir
    model_dir.mkdir(parents=True, exist_ok=True)

    model = whisperx.load_model(
        model_name,
        device,
        compute_type=compute_type,
        vad_method=vad_method,
        download_root=str(model_dir),
    )
    audio_data = whisperx.load_audio(audio_path)
    result = model.transcribe(audio_data, batch_size=batch_size)
    language = str(result.get("language") or "en")
    segments = result.get("segments") or []

    # Free the transcription model before loading the alignment model to
    # halve peak memory on small machines.
    del model
    try:
        import gc

        gc.collect()
    except Exception:
        pass

    try:
        align_model, metadata = whisperx.load_align_model(
            language_code=language, device=device, model_dir=str(model_dir)
        )
        aligned = whisperx.align(segments, align_model, metadata, audio_data, device, return_char_alignments=False)
        segments = aligned.get("segments") or segments
    except Exception as exc:  # alignment is best-effort; segment timing still works
        print(f"alignment skipped: {exc}", file=sys.stderr)

    payload = {
        "language": language,
        "segments": [
            {
                "start": float(segment.get("start") or 0),
                "end": float(segment.get("end") or 0),
                "text": str(segment.get("text") or ""),
                "words": [
                    {
                        "start": float(word["start"]),
                        "end": float(word["end"]),
                        "word": str(word.get("word") or ""),
                    }
                    for word in (segment.get("words") or [])
                    if word.get("start") is not None and word.get("end") is not None
                ],
            }
            for segment in segments
        ],
    }
    Path(out_path).write_text(json.dumps(payload), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
