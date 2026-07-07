#!/usr/bin/env python3

import json
import math
import mimetypes
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import wave
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse


def relaunch_inside_local_venv() -> None:
    if os.environ.get("AVATAR_TAX_NO_VENV_REEXEC") == "1":
        return

    app_root = Path(__file__).resolve().parent
    venv_python = app_root / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        return

    try:
        current_python = Path(sys.executable).resolve()
        target_python = venv_python.resolve()
    except OSError:
        current_python = Path(sys.executable)
        target_python = venv_python

    if current_python == target_python:
        return

    os.environ["AVATAR_TAX_NO_VENV_REEXEC"] = "1"
    os.execv(str(venv_python), [str(venv_python), str(app_root / Path(__file__).name), *sys.argv[1:]])


relaunch_inside_local_venv()

import requests
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from PIL import Image, ImageFilter, ImageOps, ImageTk
except ImportError as exc:
    raise RuntimeError("Pillow is required. Install it with: pip install pillow") from exc


APP_TITLE = "Avatar Tax"
SETTINGS_FILE = ".avatar_tax_settings.json"
SERPER_ENDPOINT = "https://google.serper.dev/images"
DEROUTER_BASE_URL = "https://api.derouter.ai/openai/v1"
DLL_DIRECTORY_HANDLES: Dict[str, Any] = {}

DEFAULT_OPENAI_MODEL = "gpt-5-mini"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_DEROUTER_GPT_MODEL = "gpt-5.4"
DEFAULT_DEROUTER_CLAUDE_MODEL = "claude-sonnet-4-6"

PLANNING_PROVIDER_LABELS = {
    "openai": "OpenAI",
    "derouter_gpt": "Derouter GPT",
    "derouter_claude": "Derouter Claude",
    "deepseek": "DeepSeek",
    "local": "Local fallback",
}

TRANSCRIPTION_PROVIDER_LABELS = {
    "local_mac": "Local fast (word-level sync)",
    "local_whisperx": "Local WhisperX (most accurate, slower)",
    "openai_mini": "OpenAI gpt-4o-mini-transcribe",
    "none": "No transcription",
}

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
IMAGE_CHOICE_COUNT = 4
IMAGE_BREATHING_ROOM_SECONDS = 2.5
EDITORIAL_CARD_KINDS = {
    "form_highlight",
    "receipt_stack",
    "rule_slate",
    "mistake_teardown",
    "deadline_flip",
    "money_leak",
    "checklist_reveal",
    "document_scan",
}
DATA_VIZ_KINDS = {"stat_counter", "bar_chart", "donut_chart"}
AVATAR_CALLOUT_KINDS = {"soft_caption", "underline_callout", "strike_callout", "mistake_strip"}
LEGACY_CARD_KIND_MAP = {
    "tax_card": "form_highlight",
    "warning_card": "mistake_strip",
    "deadline_card": "deadline_flip",
    "money_card": "underline_callout",
    "checklist_card": "checklist_reveal",
}
SAFE_OVERLAY_KINDS = EDITORIAL_CARD_KINDS | AVATAR_CALLOUT_KINDS | DATA_VIZ_KINDS | {"title_card"}
MIN_IMAGE_WIDTH = 900
MIN_IMAGE_HEIGHT = 500
MIN_IMAGE_RATIO = 1.15
MAX_IMAGE_RATIO = 2.1
MAX_TEXT_EDGE_DENSITY = 0.34
DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
    )
}
BLOCKED_IMAGE_DOMAINS = (
    "stockcake",
    "dreamstime",
    "alamy",
    "shutterstock",
    "istockphoto",
    "gettyimages",
    "depositphotos",
    "123rf",
    "adobestock",
    "freepik",
    "vecteezy",
    "pngtree",
    "canva",
    "pinterest",
    "facebook",
    "instagram",
    "tiktok",
    "youtube",
    "ytimg",
)
BAD_IMAGE_TERMS = (
    "thumbnail",
    "maxresdefault",
    "hqdefault",
    "mqdefault",
    "poster",
    "logo",
    "icon",
    "vector",
    "illustration",
    "cartoon",
    "clipart",
    "infographic",
    "meme",
    "collage",
    "template",
    "banner",
    "cover-art",
    "royalty-free",
    "stock photo",
)
CLEAN_IMAGE_SUFFIX = " photo -stock -illustration -clipart -vector"
RETIREMENT_TERMS_RE = re.compile(
    r"\b(retire|retiree|retirement|401\s?\(?k\)?|403\s?\(?b\)?|ira|roth|rmd|rmds|required minimum|"
    r"social security|pension|annuity|annuities|medicare|nest egg|withdrawal|withdrawals|catch[- ]?up)\b",
    re.IGNORECASE,
)


@dataclass
class PlannedImage:
    index: int
    time: float
    duration: float
    query: str
    caption: str
    cue: str = ""
    path: str = ""
    source: str = ""
    use: bool = True
    selected: int = 0
    choices: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TranscriptChunk:
    start: float
    end: float
    text: str


@dataclass
class TranscriptWord:
    start: float
    end: float
    text: str


@dataclass
class SpeechSpan:
    start: float
    end: float
    text: str
    words: List["TranscriptWord"] = field(default_factory=list)


@dataclass
class TranscriptResult:
    text: str
    chunks: List[TranscriptChunk] = field(default_factory=list)
    words: List[TranscriptWord] = field(default_factory=list)


@dataclass
class DirectorPlan:
    title: str
    duration: float
    chapters: List[Dict[str, Any]] = field(default_factory=list)
    overlays: List[Dict[str, Any]] = field(default_factory=list)
    zooms: List[Dict[str, Any]] = field(default_factory=list)
    images: List[PlannedImage] = field(default_factory=list)
    segments: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class BuildJob:
    video: Path
    stem: str
    title: str
    duration: float
    work_dir: Path
    public_dir: Path
    avatar_public: Path
    plan: DirectorPlan
    zip_path: Optional[Path] = None
    status: str = "review"


def safe_stem(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", text.strip())
    return cleaned.strip("_") or "avatar_video"


def load_settings(root: Path) -> Dict[str, Any]:
    try:
        return json.loads((root / SETTINGS_FILE).read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(root: Path, settings: Dict[str, Any]) -> None:
    try:
        (root / SETTINGS_FILE).write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception:
        pass


def provider_key(label: str) -> str:
    for key, value in PLANNING_PROVIDER_LABELS.items():
        if value == label:
            return key
    return "openai"


def transcription_key(label: str) -> str:
    for key, value in TRANSCRIPTION_PROVIDER_LABELS.items():
        if value == label:
            return key
    return "local_mac"


def default_model(provider: str) -> str:
    if provider == "deepseek":
        return os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL)
    if provider == "derouter_gpt":
        return os.getenv("DEROUTER_GPT_MODEL", DEFAULT_DEROUTER_GPT_MODEL)
    if provider == "derouter_claude":
        return os.getenv("DEROUTER_CLAUDE_MODEL", DEFAULT_DEROUTER_CLAUDE_MODEL)
    if provider == "local":
        return "local"
    return os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)


def api_key_for(provider: str) -> str:
    if provider == "deepseek":
        return os.getenv("DEEPSEEK_API_KEY", "").strip()
    if provider.startswith("derouter"):
        return os.getenv("DEROUTER_API_KEY", "").strip()
    if provider == "local":
        return ""
    return os.getenv("OPENAI_API_KEY", "").strip()


def client_for(provider: str) -> Optional[OpenAI]:
    if OpenAI is None or provider == "local":
        return None
    key = api_key_for(provider)
    if not key:
        return None
    kwargs: Dict[str, Any] = {"api_key": key}
    if provider == "deepseek":
        kwargs["base_url"] = "https://api.deepseek.com"
    elif provider.startswith("derouter"):
        kwargs["base_url"] = os.getenv("DEROUTER_BASE_URL", DEROUTER_BASE_URL)
    return OpenAI(**kwargs)


def service_label(service: str) -> str:
    return {
        "serper": "Serper",
        "openai": "OpenAI",
        "openai_mini": "OpenAI transcription",
        "deepseek": "DeepSeek",
        "derouter_gpt": "Derouter",
        "derouter_claude": "Derouter",
        "derouter": "Derouter",
    }.get(service, service.replace("_", " ").title())


def service_env_var(service: str) -> str:
    if service == "serper":
        return "SERPER_API_KEY"
    if service in {"derouter", "derouter_gpt", "derouter_claude"}:
        return "DEROUTER_API_KEY"
    if service == "deepseek":
        return "DEEPSEEK_API_KEY"
    return "OPENAI_API_KEY"


def recoverable_api_error(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = (
        "401",
        "402",
        "403",
        "524",
        "429",
        "timeout",
        "retryable",
        "not configured",
        "missing",
        "missing key",
        "api_key",
        "invalid token",
        "invalid api key",
        "incorrect api key",
        "invalid_request_error",
        "quota",
        "credit",
        "billing",
        "balance",
        "insufficient",
        "resource_exhausted",
        "rate limit",
        "too many requests",
        "payment required",
        "unauthorized",
    )
    return any(marker in text for marker in markers)


def brief_error(exc: Exception, max_len: int = 900) -> str:
    text = clean_text(str(exc))
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "..."


def set_env_file_value(env_path: Path, key: str, value: str) -> None:
    lines: List[str] = []
    found = False
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    updated: List[str] = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            updated.append(f"{key}={value}")
            found = True
        else:
            updated.append(line)
    if not found:
        updated.append(f"{key}={value}")
    env_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def run_command(args: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)


def ffprobe_duration(path: Path) -> float:
    output = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    ).stdout.strip()
    return max(1.0, float(output))


def extract_audio(video: Path, audio_out: Path) -> None:
    audio_out.parent.mkdir(parents=True, exist_ok=True)
    run_command(["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "96k", str(audio_out)])


def prepare_stable_avatar_video(video: Path, video_out: Path) -> None:
    video_out.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video),
            "-vf",
            "fps=30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(video_out),
        ]
    )


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str) -> List[str]:
    text = clean_text(text)
    if not text:
        return []
    chunks = re.split(r"(?<=[.!?])\s+", text)
    return [c.strip() for c in chunks if c.strip()]


def approximate_transcript_chunks(text: str, duration: float, target_seconds: float = 8.0) -> List[TranscriptChunk]:
    sentences = split_sentences(text)
    if not sentences:
        return []
    words_total = max(1, sum(len(sentence.split()) for sentence in sentences))
    chunks: List[TranscriptChunk] = []
    cursor = 0.0
    bucket: List[str] = []
    bucket_words = 0
    target_words = max(20, int(words_total * target_seconds / max(duration, 1.0)))

    for sentence in sentences:
        words = max(1, len(sentence.split()))
        bucket.append(sentence)
        bucket_words += words
        if bucket_words >= target_words:
            chunk_duration = duration * bucket_words / words_total
            end = min(duration, cursor + chunk_duration)
            chunks.append(TranscriptChunk(round(cursor, 2), round(end, 2), clean_text(" ".join(bucket))))
            cursor = end
            bucket = []
            bucket_words = 0

    if bucket:
        chunks.append(TranscriptChunk(round(cursor, 2), round(duration, 2), clean_text(" ".join(bucket))))
    return chunks


def transcript_chunks_for_prompt(chunks: List[TranscriptChunk], duration: float) -> str:
    if not chunks:
        return ""
    lines: List[str] = []
    for chunk in chunks:
        if chunk.end < 0 or chunk.start > duration:
            continue
        text = clean_text(chunk.text)
        if not text:
            continue
        lines.append(f"[{chunk.start:07.2f}-{chunk.end:07.2f}] {text[:520]}")
    return "\n".join(lines[:260])


_FASTER_WHISPER_CACHE: Dict[str, Any] = {}


def transcribe_local(audio: Path, log: Any) -> TranscriptResult:
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        raise RuntimeError("faster-whisper is not installed. Use OpenAI transcription or install it.") from exc

    model_name = os.getenv("WHISPER_MODEL", "base")
    device = os.getenv("WHISPER_DEVICE", "cpu")
    compute_type = os.getenv("WHISPER_COMPUTE", "int8")
    cache_key = f"{model_name}|{device}|{compute_type}"
    model = _FASTER_WHISPER_CACHE.get(cache_key)
    if model is None:
        log(f"Loading faster-whisper model ({model_name})...")
        model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
            cpu_threads=max(4, os.cpu_count() or 4),
        )
        _FASTER_WHISPER_CACHE[cache_key] = model
    log(f"Transcribing locally with faster-whisper ({model_name})...")
    segments, _info = model.transcribe(
        str(audio),
        vad_filter=True,
        word_timestamps=True,
        beam_size=1,
        condition_on_previous_text=False,
    )
    chunks: List[TranscriptChunk] = []
    words: List[TranscriptWord] = []
    parts: List[str] = []
    for segment in segments:
        text = clean_text(segment.text.strip())
        if not text:
            continue
        parts.append(text)
        chunks.append(TranscriptChunk(round(float(segment.start), 2), round(float(segment.end), 2), text))
        for word in segment.words or []:
            token = clean_text(str(word.word or ""))
            if token:
                words.append(TranscriptWord(round(float(word.start), 2), round(float(word.end), 2), token))
    return TranscriptResult(clean_text(" ".join(parts)), chunks, words)


def transcribe_whisperx(audio: Path, log: Any) -> TranscriptResult:
    """Run WhisperX in an isolated child process. A crash, hang, or OOM in
    torch/ctranslate2 kills only the child; the GUI keeps running and the
    caller falls back to faster-whisper."""
    app_root = Path(__file__).resolve().parent
    runner = app_root / "whisperx_runner.py"
    if not runner.exists():
        raise RuntimeError("whisperx_runner.py is missing next to the app.")

    model_name = os.getenv("WHISPERX_MODEL", os.getenv("WHISPER_MODEL", "base"))
    timeout_seconds = int(os.getenv("WHISPERX_TIMEOUT", "1800"))
    out_json = audio.with_suffix(".whisperx.json")
    out_json.unlink(missing_ok=True)

    log(f"Transcribing with WhisperX ({model_name}) in an isolated process...")
    kwargs: Dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    try:
        proc = subprocess.run(
            [sys.executable, str(runner), str(audio), str(out_json)],
            cwd=app_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            **kwargs,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"WhisperX timed out after {timeout_seconds}s.") from exc
    if proc.returncode != 0 or not out_json.exists():
        tail = clean_text(proc.stdout or "")[-500:]
        raise RuntimeError(f"WhisperX process failed (code {proc.returncode}). {tail}")

    data = json.loads(out_json.read_text(encoding="utf-8"))
    out_json.unlink(missing_ok=True)
    chunks: List[TranscriptChunk] = []
    words: List[TranscriptWord] = []
    parts: List[str] = []
    for segment in data.get("segments") or []:
        text = clean_text(str(segment.get("text") or ""))
        if not text:
            continue
        parts.append(text)
        chunks.append(
            TranscriptChunk(round(float(segment.get("start") or 0), 2), round(float(segment.get("end") or 0), 2), text)
        )
        for word in segment.get("words") or []:
            token = clean_text(str(word.get("word") or ""))
            if token:
                words.append(TranscriptWord(round(float(word["start"]), 2), round(float(word["end"]), 2), token))
    if words:
        log(f"WhisperX word-level alignment complete ({len(words)} timed words).")
    else:
        log("WhisperX finished with segment timing only.")
    return TranscriptResult(clean_text(" ".join(parts)), chunks, words)


def words_from_chunks(chunks: List[TranscriptChunk]) -> List[TranscriptWord]:
    """Approximate word timing by spreading each chunk's words across its span.
    Used when the transcription backend gives no word-level timestamps."""
    words: List[TranscriptWord] = []
    for chunk in chunks:
        tokens = chunk.text.split()
        if not tokens:
            continue
        span = max(0.2, chunk.end - chunk.start)
        step = span / len(tokens)
        for i, token in enumerate(tokens):
            start = chunk.start + i * step
            words.append(TranscriptWord(round(start, 2), round(min(chunk.end, start + step), 2), token))
    return words


def transcribe_openai(audio: Path, log: Any) -> TranscriptResult:
    if OpenAI is None:
        raise RuntimeError("openai package is not installed.")
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is missing.")
    log("Transcribing with OpenAI gpt-4o-mini-transcribe...")
    client = OpenAI(api_key=key)
    with audio.open("rb") as fh:
        response = client.audio.transcriptions.create(
            model=os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe"),
            file=fh,
            response_format="text",
        )
    return TranscriptResult(clean_text(str(response)), [])


def local_plan(title: str, transcript: str, duration: float, image_target: Optional[int] = None) -> DirectorPlan:
    sentences = split_sentences(transcript)
    chapters: List[Dict[str, Any]] = []
    overlays: List[Dict[str, Any]] = []
    zooms: List[Dict[str, Any]] = []
    images: List[PlannedImage] = []

    chapter_len = 65 if duration < 900 else 85
    chapter_count = max(1, math.ceil(duration / chapter_len))
    for i in range(chapter_count):
        start = i * chapter_len
        end = min(duration, start + chapter_len)
        text = sentences[min(i * max(1, len(sentences) // chapter_count), max(0, len(sentences) - 1))] if sentences else title
        headline = headline_from_sentence(text, fallback=f"Point {i + 1}")
        chapters.append({"number": i + 1, "start": start, "end": end, "title": headline})
        card_time = 6.2 if i == 0 else start
        if card_time < duration - 2.5:
            overlays.append(
                {
                    "kind": "title_card",
                    "time": card_time,
                    "duration": 2.6,
                    "text": headline,
                    "number": i + 1,
                    "sfx": "hit",
                }
            )

    beat = 0.0
    k = 0
    opening_segments = [1.7, 2.1, 1.85, 2.4, 2.0, 2.25]
    opening_scales = [1.045, 1.08, 1.035, 1.075, 1.05, 1.085]
    later_segments = [6.0, 7.5, 8.0, 6.8]
    later_scales = [1.025, 1.05, 1.035, 1.065]
    x_positions = [-0.55, 0.45, 0, 0.65, -0.45, 0.25]
    y_positions = [0.06, -0.1, 0, 0.12, -0.08, 0.05]
    while beat < duration:
        if beat < 30:
            seg = opening_segments[k % len(opening_segments)]
            scale = opening_scales[k % len(opening_scales)]
            mode = "punch" if k % 3 == 1 else ("settle" if k % 3 == 2 else "slow")
        else:
            seg = later_segments[k % len(later_segments)]
            scale = later_scales[k % len(later_scales)]
            mode = "punch" if k % 5 == 2 else ("steady" if k % 4 == 0 else "slow")
        zooms.append(
            {
                "start": round(beat, 2),
                "end": round(min(duration, beat + seg), 2),
                "scale": round(scale, 3),
                "x": x_positions[k % len(x_positions)],
                "y": y_positions[k % len(y_positions)],
                "mode": mode,
            }
        )
        beat += seg
        k += 1

    image_slots = image_target if image_target is not None else target_image_count(duration, transcript)
    for i, image_seed in enumerate(image_seed_phrases(title, transcript, image_slots)):
        first_time = 24 if duration > 75 else 8
        usable_span = max(12, duration - first_time - 7)
        t = min(duration - 6, first_time + (i + 0.6) * usable_span / max(1, image_slots))
        phrase = headline_from_sentence(image_seed, fallback=title)
        images.append(
            PlannedImage(
                index=i + 1,
                time=round(t, 2),
                duration=4.2,
                query=clean_image_query(image_seed),
                caption=phrase,
                cue=clean_text(image_seed)[:140],
            )
        )

    return DirectorPlan(title=title, duration=duration, chapters=chapters, overlays=overlays, zooms=zooms, images=images)


def headline_from_sentence(sentence: str, fallback: str = "Key point") -> str:
    words = re.findall(r"[A-Za-z0-9%$]+(?:[-'][A-Za-z0-9%$]+)?", sentence)
    stop = {"the", "and", "that", "with", "from", "this", "there", "your", "about", "into", "because"}
    useful = [w for w in words if w.lower() not in stop]
    headline = " ".join(useful[:6]) or fallback
    return headline[:72]


def strip_leading_card_number(text: str) -> str:
    cleaned = clean_text(text)
    return re.sub(r"^(?:#?\d{1,2}|[IVX]{1,5})[.)\]:-]?\s+", "", cleaned, flags=re.IGNORECASE).strip() or cleaned


def title_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def looks_like_filename_title(title: str, video_stem: str) -> bool:
    if not title.strip():
        return False
    key = title_key(title)
    stem_key = title_key(video_stem)
    cleaned_stem_key = title_key(video_stem.replace("_", " ").replace("-", " "))
    return bool(key and (key == stem_key or key == cleaned_stem_key or re.fullmatch(r"(test|untitled|video)\d*", key)))


def display_title_from_transcript(raw_title: str, transcript: str, video_stem: str) -> str:
    if raw_title.strip() and not looks_like_filename_title(raw_title, video_stem):
        return clean_text(raw_title)[:80]
    for sentence in split_sentences(transcript)[:8]:
        phrase = scripted_callout(sentence, "")
        if phrase and not re.fullmatch(r"(CHECK|WATCH|DON'T MISS|IRS WATCH|CHECK EVERY FORM).*", phrase):
            return headline_from_sentence(sentence, fallback=phrase).upper()
    for sentence in split_sentences(transcript)[:8]:
        candidate = headline_from_sentence(sentence, fallback="")
        if candidate and len(candidate.split()) >= 3:
            return candidate.upper()
    if RETIREMENT_TERMS_RE.search(transcript):
        return "RETIREMENT TAX MISTAKES TO AVOID"
    return "TAX MISTAKES TO AVOID"


def target_image_count(duration: float, transcript: str) -> int:
    minutes = max(0.5, duration / 60)
    density = 2.2 if minutes <= 12 else 1.8
    target = int(round(minutes * density))
    if transcript and len(transcript.split()) < 450:
        target = max(3, min(target, 8))
    return max(3, min(32, target))


def image_seed_phrases(title: str, transcript: str, count: int) -> List[str]:
    sentences = split_sentences(transcript)
    if not sentences:
        return [title] * max(0, count)
    seeds: List[str] = []
    step = max(1, len(sentences) / max(1, count))
    for i in range(count):
        idx = min(len(sentences) - 1, int(i * step + step * 0.35))
        seeds.append(sentences[idx])
    return seeds


def fallback_image_phrases(title: str) -> List[str]:
    topic = headline_from_sentence(title, fallback="tax documents")
    return [
        f"{topic} paperwork close up",
        "retired couple reviewing finances at kitchen table",
        "senior man reviewing tax documents with calculator",
        "social security card with tax forms close up",
        "401k retirement statement on desk close up",
        "IRA account paperwork with reading glasses",
        "financial advisor meeting with older couple",
        "IRS tax forms on table close up",
        "person reviewing tax documents at desk",
        "calculator forms and receipts close up",
        "retirement savings piggy bank with coins",
        "deadline calendar paperwork close up",
        "medicare enrollment forms on table",
        "senior woman using laptop for online banking",
        "pension check and bank statement close up",
        "accountant reviewing documents office",
        "tax refund form close up",
        "stack of receipts and invoices",
    ]


# Maps spoken topics to concrete, photographable subjects so Serper gets a
# visual query instead of an abstract sentence fragment.
IMAGE_TOPIC_QUERIES: List[Tuple[str, str]] = [
    (r"\b401\s?\(?k\)?|403\s?\(?b\)?\b", "401k retirement account statement on desk"),
    (r"\broth\b", "roth ira paperwork with calculator on desk"),
    (r"\bira\b", "ira retirement account documents close up"),
    (r"\brmd|required minimum\b", "senior reviewing retirement account withdrawal paperwork"),
    (r"\bsocial security\b", "social security card with benefit statement"),
    (r"\bpension\b", "pension statement and bank documents on table"),
    (r"\bmedicare\b", "medicare enrollment forms on table"),
    (r"\bannuit\w+\b", "annuity contract documents with pen"),
    (r"\bwithdraw\w*|distribution\b", "person withdrawing money bank statement desk"),
    (r"\baudit|irs\b", "IRS building sign washington"),
    (r"\brefund\b", "tax refund check close up"),
    (r"\bdeadline|filing|late\b", "tax deadline calendar with documents"),
    (r"\bdeduction|write[- ]?off|expense\b", "receipts and calculator tax deductions desk"),
    (r"\bw-?2|1099|form\b", "tax forms w2 1099 on table close up"),
    (r"\bbracket|rate|percent\b", "tax bracket chart documents with calculator"),
    (r"\bsav\w+|nest egg\b", "retirement savings jar with coins close up"),
    (r"\binvest\w+|portfolio|stock\b", "retirement investment portfolio statement laptop"),
    (r"\bcouple|spouse|married\b", "older couple reviewing finances together at home"),
    (r"\badvisor|planner|cpa|accountant\b", "financial advisor meeting with retired couple"),
]


CONCRETE_IMAGE_WORDS_RE = re.compile(
    r"\b(desk|table|close.?up|person|people|couple|man|woman|senior|hands?|documents?|paperwork|"
    r"forms?|statement|check|calculator|receipts?|office|building|laptop|kitchen|meeting|jar|"
    r"coins?|calendar|card|glasses|pen|envelope|folder|sign|house|home)\b",
    re.IGNORECASE,
)


def clean_image_query(query: str) -> str:
    query = re.sub(r"\b(overpay|subscribe|like and subscribe|thumbnail)\b", "", query, flags=re.IGNORECASE)
    query = re.sub(r"\s+-\w+", "", clean_text(query))
    if not query:
        query = "tax documents desk"
    # Keep AI-authored concrete queries; remap abstract sentence fragments to a
    # photographable subject when the topic is recognizable.
    if not CONCRETE_IMAGE_WORDS_RE.search(query):
        for pattern, mapped in IMAGE_TOPIC_QUERIES:
            if re.search(pattern, query, flags=re.IGNORECASE):
                query = mapped
                break
    words = query.split()
    if len(words) > 10:
        query = " ".join(words[:10])
    if "photo" not in query.lower():
        query = f"{query}{CLEAN_IMAGE_SUFFIX}"
    return query[:140]


def image_query_attempts(query: str, caption: str, fallback_pool: List[str], index: int) -> List[str]:
    """Progressively simpler queries to retry when a search returns nothing usable."""
    attempts: List[str] = [query]
    bare = re.sub(r"\s+-\w+", "", query)
    bare = clean_text(re.sub(r"\bphoto\b", "", bare, flags=re.IGNORECASE))
    haystack = f"{bare} {caption}"
    for pattern, mapped in IMAGE_TOPIC_QUERIES:
        if re.search(pattern, haystack, flags=re.IGNORECASE):
            attempts.append(mapped)
            break
    if caption and clean_text(caption).lower() not in query.lower():
        attempts.append(clean_image_query(caption))
    if fallback_pool:
        attempts.append(clean_image_query(fallback_pool[index % len(fallback_pool)]))
    unique: List[str] = []
    seen: set[str] = set()
    for attempt in attempts:
        key = attempt.lower()
        if attempt and key not in seen:
            seen.add(key)
            unique.append(attempt)
    return unique[:4]


def opening_overlay_specs(title: str, transcript: str, duration: float) -> List[Dict[str, Any]]:
    opening = min(duration, 30)
    if opening < 10:
        return []
    hook = first_impact_phrase(title, transcript)
    opening_label = "RETIREMENT TAXES" if RETIREMENT_TERMS_RE.search(transcript or title) else "TAX MISTAKES"
    specs = [
        {
            "kind": "money_leak",
            "time": 6.2,
            "duration": 3.8,
            "text": hook,
            "label": opening_label,
            "tone": infer_card_tone(hook),
            "icon": "warning",
            "sfx": "hit",
        },
    ]
    if re.search(r"\bsoftware\b.{0,80}\balways right\b", transcript, re.IGNORECASE | re.DOTALL):
        specs.append(
            {
                "kind": "strike_callout",
                "time": 12.4,
                "duration": 3.0,
                "text": "SOFTWARE IS ALWAYS RIGHT",
                "label": "COMMON MISTAKE",
                "tone": "warning",
                "icon": "warning",
                "sfx": "hit",
            }
        )
    return [spec for spec in specs if float(spec["time"]) + float(spec["duration"]) < opening + 2]


def section_title_overlays(
    transcript: str,
    duration: float,
    transcript_chunks: List[TranscriptChunk],
) -> List[Dict[str, Any]]:
    chunks = transcript_chunks or approximate_transcript_chunks(transcript, duration, target_seconds=5.5)
    if not chunks:
        return []

    used_titles: set[str] = set()
    overlays: List[Dict[str, Any]] = []
    next_number = 1
    ordinal_numbers = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
        "seventh": 7,
        "eighth": 8,
        "ninth": 9,
        "tenth": 10,
    }

    def add_card(timepoint: float, headline: str, number: Optional[int] = None) -> None:
        nonlocal next_number
        headline = normalize_section_title(headline)
        if not headline:
            return
        key = re.sub(r"[^a-z0-9]+", "", headline.lower())
        if key in used_titles:
            return
        used_titles.add(key)
        card_number = number or next_number
        next_number = max(next_number, card_number + 1)
        overlays.append(
            {
                "kind": "title_card",
                "time": round(clamp_float(timepoint, 7.0, duration - 5.0), 2),
                "duration": 2.8,
                "text": headline,
                "number": card_number,
                "accent": "yellow",
                "section_turn": True,
                "sfx": "whoosh",
            }
        )

    for chunk in chunks:
        sentences = split_sentences(chunk.text)
        if not sentences:
            continue
        cursor = 0
        chunk_lower = chunk.text.lower()
        for index, sentence in enumerate(sentences):
            sentence_lower = sentence.lower()
            local_pos = chunk_lower.find(sentence_lower, cursor)
            if local_pos < 0:
                local_pos = cursor
            cursor = max(cursor, local_pos + len(sentence))
            relative = local_pos / max(1, len(chunk.text))
            timepoint = chunk.start + relative * max(0.2, chunk.end - chunk.start)

            start_match = re.search(r"\bstart with\b\s+(.+)", sentence, flags=re.IGNORECASE)
            if start_match:
                add_card(timepoint + 0.4, start_match.group(1), 1)
                continue

            mistake_match = re.search(
                r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|final|last)\s+mistake\b(?:\s*(?:is|was|means|about|:|,|-)\s*(.*))?",
                sentence,
                flags=re.IGNORECASE,
            )
            if not mistake_match:
                continue

            ordinal = mistake_match.group(1).lower()
            card_number = ordinal_numbers.get(ordinal)
            if card_number is None:
                card_number = max(next_number, 3)
            candidate = clean_text(mistake_match.group(2) or "")
            if not candidate and index + 1 < len(sentences):
                candidate = sentences[index + 1]
            if not candidate:
                candidate = f"{ordinal} mistake"
            add_card(timepoint + 0.5, candidate, card_number)

    return overlays


GENERIC_TITLE_ORDINALS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}


def generic_title_number(text: str, explicit_number: Any = None) -> Optional[int]:
    try:
        if explicit_number is not None and str(explicit_number).strip():
            return int(float(str(explicit_number).strip()))
    except (TypeError, ValueError):
        pass
    lower = clean_text(text).lower()
    for word, number in GENERIC_TITLE_ORDINALS.items():
        if re.search(rf"\b{word}\b", lower):
            return number
    number_match = re.search(r"\b(?:mistake|part|step|section)\s*#?\s*(\d{1,2})\b", lower)
    return int(number_match.group(1)) if number_match else None


def is_generic_section_title(text: str) -> bool:
    lower = clean_text(strip_leading_card_number(text)).lower()
    lower = re.sub(r"[^a-z0-9# ]+", " ", lower)
    lower = re.sub(r"\s+", " ", lower).strip()
    if not lower:
        return False
    ordinal = "|".join(list(GENERIC_TITLE_ORDINALS.keys()) + ["final", "last"])
    return bool(
        re.fullmatch(rf"(?:{ordinal})(?: tax| common| major| hidden)? mistake", lower)
        or re.fullmatch(r"(?:tax |common |major |hidden )?mistake\s*#?\d*", lower)
        or re.fullmatch(r"(?:next|final|last) point", lower)
    )


def repair_generic_title_cards(
    overlays: List[Dict[str, Any]],
    section_titles: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_number: Dict[int, str] = {}
    timed_sections: List[Tuple[float, str, Optional[int]]] = []
    for card in section_titles:
        text = clean_text(str(card.get("text") or "")).upper()
        if not text or is_generic_section_title(text):
            continue
        number = generic_title_number(text, card.get("number"))
        if number is not None:
            by_number[number] = text
        timed_sections.append((float(card.get("time") or 0), text, number))

    fixed: List[Dict[str, Any]] = []
    for raw in overlays:
        kind = LEGACY_CARD_KIND_MAP.get(str(raw.get("kind") or ""), str(raw.get("kind") or ""))
        if kind != "title_card":
            fixed.append(raw)
            continue

        raw_text = clean_text(str(raw.get("text") or ""))
        text = strip_leading_card_number(raw_text)
        if not is_generic_section_title(text):
            fixed.append(raw)
            continue

        number = generic_title_number(text, raw.get("number"))
        replacement = by_number.get(number) if number is not None else None
        if not replacement and timed_sections:
            timepoint = float(raw.get("time") or 0)
            close = sorted(timed_sections, key=lambda section: abs(section[0] - timepoint))
            if close and abs(close[0][0] - timepoint) <= 22:
                replacement = close[0][1]
                if number is None:
                    number = close[0][2]
        if not replacement:
            continue

        repaired = dict(raw)
        repaired["text"] = replacement
        if number is not None:
            repaired["number"] = number
        repaired["section_turn"] = True
        fixed.append(repaired)
    return fixed


def protect_section_title_cards(
    overlays: List[Dict[str, Any]],
    section_titles: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    protected = [
        float(card.get("time") or 0)
        for card in section_titles
        if not is_generic_section_title(str(card.get("text") or ""))
    ]
    if not protected:
        return overlays
    protected_kinds = EDITORIAL_CARD_KINDS | {"title_card"}
    clean: List[Dict[str, Any]] = []
    for raw in overlays:
        kind = LEGACY_CARD_KIND_MAP.get(str(raw.get("kind") or ""), str(raw.get("kind") or ""))
        if raw.get("section_turn") or kind not in protected_kinds:
            clean.append(raw)
            continue
        timepoint = float(raw.get("time") or 0)
        if any(abs(timepoint - section_time) < 6.5 for section_time in protected):
            continue
        clean.append(raw)
    return clean


def normalize_section_title(text: str) -> str:
    cleaned = clean_text(text)
    cleaned = re.sub(r"^[.:,;\-\s]+", "", cleaned)
    cleaned = re.sub(r"^(?:forgetting|checking|verify|start with|thinking)\s+", "", cleaned, flags=re.IGNORECASE)
    lower = cleaned.lower()
    if re.search(r"\bonly applies\b.{0,80}\bbusiness owners\b", lower) or re.search(r"\bapplies to business owners\b", lower):
        return "NOT JUST BUSINESS OWNERS"
    if re.search(r"\bdeductible expenses?\b|\bdeductions?\b", lower):
        return "DEDUCTIBLE EXPENSES"
    if re.search(r"\bhidden taxable income\b|\btaxable income\b", lower):
        return "HIDDEN TAXABLE INCOME"
    if re.search(r"\bsoftware\b.{0,50}\bright\b", lower):
        return "SOFTWARE IS NOT ENOUGH"
    return headline_from_sentence(cleaned, fallback="KEY POINT").upper()


def first_impact_phrase(title: str, transcript: str) -> str:
    for sentence in split_sentences(transcript)[:6]:
        text = sentence.lower()
        if re.search(r"\boverpay|overpaid|pay too much|leaving money|lose money|losing money\b", text):
            return "LOSING MONEY QUIETLY"
        if re.search(r"\bmistake|mistakes|wrong|error\b", text):
            return "TAX MISTAKES COST"
        if re.search(r"\bdeduction|deductions|write[- ]?off\b", text):
            return "DON'T MISS DEDUCTIONS"
        if re.search(r"\bhidden|missed|secret|quietly\b", text):
            return headline_from_sentence(sentence, fallback=title).upper()
    phrases = editorial_phrases(title, transcript, 1)
    return (phrases[0] if phrases else headline_from_sentence(title, fallback="TAX MISTAKES")).upper()


def editorial_phrases(title: str, transcript: str, count: int) -> List[str]:
    phrases: List[str] = []
    seen: set[str] = set()
    for sentence in split_sentences(transcript):
        phrase = scripted_callout(sentence, title)
        key = re.sub(r"[^a-z0-9]+", "", phrase.lower())
        if phrase and key not in seen:
            seen.add(key)
            phrases.append(phrase)
        if len(phrases) >= count:
            break
    for phrase in fallback_callouts(title):
        key = re.sub(r"[^a-z0-9]+", "", phrase.lower())
        if key not in seen:
            seen.add(key)
            phrases.append(phrase)
        if len(phrases) >= count:
            break
    return phrases[:count]


def scripted_callout(sentence: str, title: str) -> str:
    text = sentence.lower()
    if re.search(r"\boverpay|overpaid|pay too much\b", text):
        return "STOP OVERPAYING"
    if re.search(r"\brmd|required minimum\b", text):
        return "RMDs ARE NOT OPTIONAL"
    if re.search(r"\bsocial security\b.{0,60}\btax", text):
        return "SOCIAL SECURITY GETS TAXED"
    if re.search(r"\bemployer match|company match|free money\b", text):
        return "FREE MONEY MISSED"
    if re.search(r"\broth\b.{0,50}\b(convert|conversion)\b", text):
        return "ROTH CONVERSION WINDOW"
    if re.search(r"\bwithdraw\w*\b.{0,60}\b(penalty|early|59)\b", text):
        return "EARLY WITHDRAWAL PENALTY"
    if re.search(r"\bcatch[- ]?up\b", text):
        return "CATCH-UP CONTRIBUTIONS"
    if re.search(r"\bdeduction|deductions|write[- ]?off\b", text):
        return "DON'T MISS DEDUCTIONS"
    if re.search(r"\bmistake|mistakes|wrong|error\b", text):
        return "SMALL MISTAKES ADD UP"
    if re.search(r"\b2026|rule|rules|changed|changes|new law\b", text):
        return "2026 RULE CHANGES"
    if re.search(r"\birs|audit|audits|penalty|penalties\b", text):
        return "IRS WATCH"
    if re.search(r"\bdeadline|deadlines|late|filing\b", text):
        return "DEADLINES MATTER"
    if re.search(r"\brefund|refunds\b", text):
        return "PROTECT YOUR REFUND"
    if re.search(r"\bbracket|brackets\b", text):
        return "KNOW YOUR BRACKET"
    if re.search(r"\bbusiness|freelancer|retiree|student|employee\b", text):
        return "NOT JUST BUSINESS OWNERS"
    if re.search(r"\bform|forms|paperwork|receipt|receipts\b", text):
        return "CHECK EVERY FORM"
    return headline_from_sentence(sentence, fallback=title).upper()


def fallback_callouts(title: str) -> List[str]:
    base = headline_from_sentence(title, fallback="Key point").upper()
    return [
        base,
        "CHECK THIS FIRST",
        "DON'T MISS THIS",
        "WATCH THE DETAILS",
        "THE RULES CHANGED",
        "SMALL ERRORS COST MONEY",
    ]


def opening_zoom_events(duration: float) -> List[Dict[str, Any]]:
    end = min(duration, 30)
    if end <= 0:
        return []
    events: List[Dict[str, Any]] = []
    t = 0.0
    prev_scale = 1.0
    pattern = [
        (0.8, 1.14, 0.0, -0.04, "flash"),
        (1.2, 1.04, 0.0, 0.0, "settle"),
        (3.8, 1.035, 0.12, 0.0, "slow"),
        (1.8, 1.082, -0.45, 0.0, "punch"),
        (4.3, 1.045, 0.45, 0.0, "settle"),
        (2.0, 1.075, 0.7, -0.1, "punch"),
        (4.8, 1.035, -0.35, 0.08, "slow"),
        (2.1, 1.08, 0.0, 0.0, "punch"),
        (5.2, 1.04, 0.35, 0.0, "settle"),
        (3.6, 1.06, -0.25, 0.1, "slow"),
    ]
    i = 0
    while t < end - 0.05:
        seg, scale, x, y, mode = pattern[i % len(pattern)]
        event_end = min(end, t + seg)
        events.append(
            {
                "start": round(t, 2),
                "end": round(event_end, 2),
                "fromScale": round(prev_scale, 3),
                "scale": scale,
                "x": x,
                "y": y,
                "mode": mode,
            }
        )
        prev_scale = scale
        t = event_end
        i += 1
    return events


def enforce_opening_flash_zoom(raw_zooms: List[Dict[str, Any]], duration: float) -> List[Dict[str, Any]]:
    if duration <= 0:
        return raw_zooms
    opening = [
        {
            "start": 0.0,
            "end": min(0.8, duration),
            "fromScale": 1.0,
            "scale": 1.14,
            "x": 0.0,
            "y": -0.04,
            "mode": "flash",
        }
    ]
    if duration > 0.8:
        opening.append(
            {
                "start": 0.8,
                "end": min(2.0, duration),
                "fromScale": 1.14,
                "scale": 1.04,
                "x": 0.0,
                "y": 0.0,
                "mode": "settle",
            }
        )
    rest = [zoom for zoom in raw_zooms if float(zoom.get("start") or 0) >= 2.0]
    return opening + rest


def generated_zoom_segments(start: float, end: float, previous_scale: float = 1.03) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    t = start
    i = 0
    scales = [1.025, 1.05, 1.035, 1.065, 1.04, 1.075]
    while t < end - 0.2:
        seg = 6.2 + (i % 4) * 1.25
        event_end = min(end, t + seg)
        scale = scales[i % len(scales)]
        events.append(
            {
                "start": round(t, 2),
                "end": round(event_end, 2),
                "fromScale": round(previous_scale, 3),
                "scale": scale,
                "x": [-0.55, 0.45, 0, 0.65, -0.45, 0.25][i % 6],
                "y": [0.06, -0.1, 0, 0.12, -0.08, 0.05][i % 6],
                "mode": "punch" if i % 5 == 2 else ("slow" if i % 4 else "steady"),
            }
        )
        previous_scale = scale
        t = event_end
        i += 1
    return events


SYNC_TOKEN_RE = re.compile(r"[a-z0-9]+")


def speech_sentence_spans(words: List[TranscriptWord], max_span_seconds: float = 14.0) -> List[SpeechSpan]:
    """Group word timestamps into spoken sentences so visuals can hold for the
    exact time a point is being made."""
    spans: List[SpeechSpan] = []
    bucket: List[TranscriptWord] = []

    def flush(end: float) -> None:
        if bucket:
            spans.append(SpeechSpan(bucket[0].start, end, " ".join(w.text for w in bucket), list(bucket)))

    for word in words:
        if bucket and word.start - bucket[-1].end > 1.6:
            flush(bucket[-1].end)
            bucket = []
        bucket.append(word)
        ends_sentence = bool(re.search(r"[.!?]$", word.text))
        too_long = word.end - bucket[0].start >= max_span_seconds
        if ends_sentence or too_long:
            flush(word.end)
            bucket = []
    flush(bucket[-1].end if bucket else 0.0)
    return [span for span in spans if span.end > span.start]


def sync_tokens(*texts: Any) -> set[str]:
    tokens: set[str] = set()
    for text in texts:
        for token in SYNC_TOKEN_RE.findall(str(text or "").lower().replace(",", "").replace("$", " ").replace("%", " ")):
            if token in STAT_HEADLINE_STOP:
                continue
            if len(token) < 3 and not token.isdigit():
                continue
            tokens.add(token)
    return tokens


def sync_token_weight(token: str) -> int:
    if token.isdigit():
        return 3
    if len(token) >= 6:
        return 2
    return 1


def find_speech_anchor(
    spans: List[SpeechSpan],
    timepoint: float,
    tokens: set[str],
    window_before: float = 12.0,
    window_after: float = 20.0,
) -> Optional[Tuple[int, float]]:
    """Find the spoken sentence this visual belongs to and the exact moment
    its first matching word is said. Weighted tokens (numbers > long words >
    short words) with a confidence threshold: a vague 1-word overlap far from
    the planned time is treated as no match, so we never confidently place a
    visual on the wrong sentence."""
    best: Optional[Tuple[int, float]] = None
    best_key = (0.0, float("inf"))
    for index, span in enumerate(spans):
        if span.end < timepoint - window_before or span.start > timepoint + window_after:
            continue
        matched = tokens & sync_tokens(span.text)
        if not matched:
            continue
        score = sum(sync_token_weight(token) for token in matched)
        distance = abs(span.start - timepoint)
        if score < 3 and not (score >= 2 and distance <= 7.0):
            continue
        if (score, -distance) > (best_key[0], -best_key[1]):
            anchor = span.start
            for word in span.words:
                if tokens & sync_tokens(word.text):
                    anchor = word.start
                    break
            best = (index, anchor)
            best_key = (score, distance)
    return best


def sync_duration_bounds(kind: str, progressive: bool) -> Tuple[float, float]:
    if kind == "title_card":
        return (2.0, 4.5)
    if kind in AVATAR_CALLOUT_KINDS:
        return (2.2, 8.0)
    if progressive:
        return (2.6, 6.0)
    if kind in DATA_VIZ_KINDS:
        return (3.0, 9.0)
    return (3.0, 9.0)


def speech_hold_end(spans: List[SpeechSpan], index: int, anchor: float) -> float:
    """Hold until the sentence finishes; if the trigger word lands at the very
    end of its sentence, carry through the immediately-following sentence so
    the visual does not flash and vanish mid-thought."""
    span = spans[index]
    end = span.end
    if span.end - anchor < 1.6 and index + 1 < len(spans):
        nxt = spans[index + 1]
        if nxt.start - span.end <= 1.0:
            end = nxt.end
    return end


def sync_plan_to_speech(plan: DirectorPlan, words: List[TranscriptWord], duration: float, log: Any = None) -> DirectorPlan:
    """Snap every overlay/image to the moment the voiceover says it, and hold
    until that point finishes, like a manual edit would. Visuals without a
    confident content match keep their planned timing untouched."""
    spans = speech_sentence_spans(words)
    if not spans:
        return plan

    synced = 0
    unmatched = 0
    for overlay in plan.overlays:
        kind = str(overlay.get("kind") or "")
        timepoint = float(overlay.get("time") or 0)
        tokens = sync_tokens(
            overlay.get("cue"),
            overlay.get("text"),
            overlay.get("value"),
            " ".join(str(item) for item in (overlay.get("items") or [])),
        )
        hit = find_speech_anchor(spans, timepoint, tokens)
        if hit is None:
            unmatched += 1
            continue
        index, anchor = hit
        span = spans[index]
        # Land on the trigger word (tiny lead), unless it opens the sentence.
        start = span.start if anchor - span.start < 1.5 else anchor - 0.15
        start = max(5.5, start)
        low, high = sync_duration_bounds(kind, bool(overlay.get("progressive")))
        hold = clamp_float(speech_hold_end(spans, index, anchor) + 0.45 - start, low, high)
        if start + hold > duration - 0.5:
            hold = max(low, duration - 0.5 - start)
            if hold < low:
                continue
        overlay["time"] = round(start, 2)
        overlay["duration"] = round(hold, 2)
        synced += 1

    for image in plan.images:
        tokens = sync_tokens(image.cue, image.caption, image.query)
        hit = find_speech_anchor(spans, image.time, tokens, window_before=8.0, window_after=16.0)
        if hit is None:
            unmatched += 1
            continue
        index, anchor = hit
        span = spans[index]
        start = max(3.0, span.start if anchor - span.start < 1.5 else anchor - 0.15)
        hold = clamp_float(speech_hold_end(spans, index, anchor) + 0.45 - start, 3.5, 8.5)
        if start + hold > duration - 1.0:
            hold = max(3.0, duration - 1.0 - start)
        image.time = round(start, 2)
        image.duration = round(hold, 2)
        synced += 1

    if log:
        log(f"Speech sync: {synced} visual(s) snapped to the exact spoken moment, {unmatched} kept planned timing.")
    return resolve_visual_conflicts(plan, duration)


def resolve_visual_conflicts(plan: DirectorPlan, duration: float) -> DirectorPlan:
    """After snapping to speech, re-space everything: full-screen visuals must
    not overlap each other, and callouts must not sit on top of image inserts."""
    plan.images.sort(key=lambda item: item.time)
    plan.overlays.sort(key=lambda item: float(item.get("time") or 0))

    # Full-screen events: image inserts + every non-callout overlay.
    events: List[Tuple[float, str, Any]] = [("image", image.time, image) for image in plan.images]
    events += [
        ("card", float(overlay.get("time") or 0), overlay)
        for overlay in plan.overlays
        if str(overlay.get("kind") or "") not in AVATAR_CALLOUT_KINDS
    ]
    events.sort(key=lambda item: item[1])

    dropped_cards: set[int] = set()
    dropped_images: set[int] = set()
    previous: Optional[Tuple[str, Any]] = None
    previous_end = -999.0
    for label, start, payload in events:
        length = payload.duration if label == "image" else float(payload.get("duration") or 0)
        if start < previous_end + 0.35 and previous is not None:
            gap_start = start - 0.35
            prev_label, prev_payload = previous
            prev_start = prev_payload.time if prev_label == "image" else float(prev_payload.get("time") or 0)
            trimmed = gap_start - prev_start
            if trimmed >= 2.2:
                if prev_label == "image":
                    prev_payload.duration = round(trimmed, 2)
                else:
                    prev_payload["duration"] = round(trimmed, 2)
            else:
                # Not enough room to trim: the later, lower-priority event loses.
                # Images and data visuals beat generic cards.
                if label == "card" and str(payload.get("kind") or "") not in DATA_VIZ_KINDS:
                    dropped_cards.add(id(payload))
                    continue
                if prev_label == "card":
                    dropped_cards.add(id(prev_payload))
                elif prev_label == "image":
                    dropped_images.add(id(prev_payload))
        previous = (label, payload)
        previous_end = start + length

    plan.overlays = [o for o in plan.overlays if id(o) not in dropped_cards]
    plan.images = [img for img in plan.images if id(img) not in dropped_images]

    # Callouts may not overlap anything full-screen (images or cards): trim
    # before, slide after, or drop if there is no room either way.
    blocking_windows = [(image.time, image.time + image.duration) for image in plan.images]
    blocking_windows += [
        (float(o.get("time") or 0), float(o.get("time") or 0) + float(o.get("duration") or 0))
        for o in plan.overlays
        if str(o.get("kind") or "") not in AVATAR_CALLOUT_KINDS
    ]
    blocking_windows.sort()
    kept: List[Dict[str, Any]] = []
    for overlay in plan.overlays:
        if str(overlay.get("kind") or "") not in AVATAR_CALLOUT_KINDS:
            kept.append(overlay)
            continue
        start = float(overlay.get("time") or 0)
        length = float(overlay.get("duration") or 0)
        for lo, hi in blocking_windows:
            if start < hi and start + length > lo:
                if start < lo - 2.0:
                    length = lo - 0.3 - start
                elif hi + 2.2 < duration - 1.0:
                    start = hi + 0.3
                else:
                    length = 0
                break
        clear = length >= 1.8 and not any(start < hi and start + length > lo for lo, hi in blocking_windows)
        if clear:
            overlay["time"] = round(start, 2)
            overlay["duration"] = round(length, 2)
            kept.append(overlay)
    plan.overlays = kept

    for index, image in enumerate(plan.images, start=1):
        image.index = index
    return plan


def enhance_director_plan(
    plan: DirectorPlan,
    title: str,
    transcript: str,
    duration: float,
    image_target: int,
    keep_existing_overlays: bool = True,
    transcript_chunks: Optional[List[TranscriptChunk]] = None,
    transcript_words: Optional[List[TranscriptWord]] = None,
    log: Any = None,
) -> DirectorPlan:
    plan.images = normalize_images(
        plan.images,
        title,
        transcript,
        duration,
        image_target,
        fill_missing=not keep_existing_overlays,
    )
    raw_zooms = plan.zooms if keep_existing_overlays and plan.zooms else professional_zoom_timeline(duration)
    plan.zooms = normalize_zoom_density(enforce_opening_flash_zoom(raw_zooms, duration), duration)
    progressive = progressive_checklist_overlays(title, transcript, duration, transcript_chunks or [])
    opening = opening_overlay_specs(title, transcript, duration)
    section_titles = section_title_overlays(transcript, duration, transcript_chunks or [])
    stats = data_viz_overlays(transcript, duration, transcript_chunks or [])
    if keep_existing_overlays and plan.overlays:
        has_ai_data_viz = any(str(item.get("kind") or "") in DATA_VIZ_KINDS for item in plan.overlays)
        combined = repair_generic_title_cards(opening + section_titles + plan.overlays, section_titles)
        combined = protect_section_title_cards(combined, section_titles)
        plan.overlays = remove_conflicting_progressive_cards(combined, progressive)
        plan.overlays.extend(progressive)
        if not has_ai_data_viz:
            plan.overlays = prioritize_data_viz(plan.overlays, stats) + stats
        plan.overlays = sanitize_overlays(plan.overlays, plan.images, duration)
    else:
        derived = repair_generic_title_cards(section_titles + derive_editorial_overlays(title, transcript, duration), section_titles)
        derived = protect_section_title_cards(derived, section_titles)
        derived = remove_conflicting_progressive_cards(derived, progressive) + progressive
        derived = prioritize_data_viz(derived, stats) + stats
        plan.overlays = sanitize_overlays(opening + derived, plan.images, duration)
    words = transcript_words or (words_from_chunks(transcript_chunks) if transcript_chunks else [])
    if words:
        plan = sync_plan_to_speech(plan, words, duration, log=log)
    return plan


def professional_zoom_timeline(duration: float) -> List[Dict[str, Any]]:
    timeline = opening_zoom_events(duration)
    if duration > 30:
        last_scale = timeline[-1]["scale"] if timeline else 1.0
        timeline.extend(generated_zoom_segments(30.0, duration, float(last_scale)))
    return normalize_zoom_density(timeline, duration)


def derive_editorial_overlays(title: str, transcript: str, duration: float) -> List[Dict[str, Any]]:
    phrases = editorial_phrases(title, transcript, 32)
    overlays: List[Dict[str, Any]] = []

    callout_times = [6.2, 15.5, 28.0]
    t = 40.0
    while t < duration - 8:
        callout_times.append(t)
        t += 12.0

    phrase_i = 0
    for timepoint in callout_times:
        if timepoint >= duration - 3:
            continue
        phrase = phrases[phrase_i % len(phrases)] if phrases else headline_from_sentence(title, fallback="Key point").upper()
        tone = infer_card_tone(phrase)
        if tone in {"warning", "audit"} and phrase_i % 3 == 1:
            kind = "strike_callout"
        elif phrase_i % 5 == 3:
            kind = "soft_caption"
        else:
            kind = "underline_callout"
        overlays.append(
            {
                "kind": kind,
                "time": round(timepoint, 2),
                "duration": 3.0,
                "text": phrase,
                "value": extract_overlay_value(phrase),
                "tone": tone,
                "icon": icon_for_tone(tone),
                "accent": "white",
                "sfx": "hit" if phrase_i % 3 == 0 else "pop",
            }
        )
        phrase_i += 1

    full_card_time = 54.0
    while full_card_time < duration - 12:
        phrase = phrases[phrase_i % len(phrases)] if phrases else headline_from_sentence(title, fallback="Key point").upper()
        tone = infer_card_tone(phrase)
        kind = "money_leak" if phrase_i % 4 == 2 else "form_highlight"
        overlays.append(
            {
                "kind": kind,
                "time": round(full_card_time, 2),
                "duration": 3.9,
                "text": phrase,
                "label": label_for_tone(tone),
                "value": extract_overlay_value(phrase),
                "tone": tone,
                "icon": icon_for_tone(tone),
                "items": checklist_items_for_phrase(phrase),
                "sfx": "whoosh",
            }
        )
        phrase_i += 1
        full_card_time += 44.0

    card_number = 2
    chapter_time = 86.0
    while chapter_time < duration - 12:
        phrase = phrases[phrase_i % len(phrases)] if phrases else headline_from_sentence(title, fallback=f"Part {card_number}").upper()
        overlays.append(
            {
                "kind": "title_card",
                "time": round(chapter_time, 2),
                "duration": 2.0,
                "text": phrase,
                "number": card_number,
                "accent": "yellow",
                "sfx": "whoosh",
            }
        )
        phrase_i += 1
        card_number += 1
        chapter_time += 72.0
    return overlays


def progressive_checklist_overlays(
    title: str,
    transcript: str,
    duration: float,
    transcript_chunks: List[TranscriptChunk],
) -> List[Dict[str, Any]]:
    chunks = transcript_chunks or approximate_transcript_chunks(transcript, duration, target_seconds=7.0)
    if not chunks:
        return []
    groups = [
        {
            "title": "DEDUCT EXPENSES",
            "label": "OFTEN MISSED",
            "tone": "money",
            "icon": "dollar",
            "terms": [
                ("MILEAGE", r"\bmileage|miles|vehicle|car\b"),
                ("INTERNET", r"\binternet|wifi|wi-fi|phone bill|cell phone\b"),
                ("SOFTWARE", r"\bsoftware|subscription|subscriptions|app\b"),
                ("EQUIPMENT", r"\bequipment|computer|laptop|camera|office\b"),
                ("HOME OFFICE", r"\bhome office|workspace\b"),
            ],
        },
        {
            "title": "RETIREMENT ACCOUNTS",
            "label": "TAXED DIFFERENTLY",
            "tone": "money",
            "icon": "dollar",
            "terms": [
                ("401(K)", r"\b401\s?\(?k\)?|403\s?\(?b\)?\b"),
                ("TRADITIONAL IRA", r"\btraditional ira\b"),
                ("ROTH IRA", r"\broth\b"),
                ("PENSION", r"\bpension\b"),
                ("SOCIAL SECURITY", r"\bsocial security\b"),
                ("HSA", r"\bhsa|health savings\b"),
            ],
        },
    ]
    overlays: List[Dict[str, Any]] = []
    for group in groups:
        seen_items: List[str] = []
        last_time = -999.0
        for chunk in chunks:
            if chunk.start < 7.0 or chunk.start > duration - 4.0:
                continue
            text = chunk.text
            matches: List[Tuple[int, str]] = []
            for label, pattern in group["terms"]:
                if label in seen_items:
                    continue
                for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                    if progressive_match_is_valid(str(group["title"]), label, text, match.start(), match.end()):
                        matches.append((match.start(), label))
                        break
            matches.sort(key=lambda item: item[0])
            if not matches:
                continue
            for pos, matched in matches:
                if matched in seen_items:
                    continue
                relative = pos / max(1, len(text))
                start = max(7.0, min(duration - 4.0, chunk.start + relative * max(0.2, chunk.end - chunk.start)))
                if start - last_time < 5.6:
                    start = last_time + 5.6
                if start > duration - 4.0:
                    break
                seen_items.append(matched)
                overlays.append(
                    {
                        "kind": "checklist_reveal",
                        "time": round(start, 2),
                        "duration": 3.8 if len(seen_items) == 1 else 4.2,
                        "text": group["title"],
                        "label": group["label"],
                        "tone": group["tone"],
                        "icon": group["icon"],
                        "items": seen_items.copy(),
                        "progressive": True,
                        "sfx": "whoosh",
                    }
                )
                last_time = start
                if len(seen_items) >= 4:
                    break
            if len(seen_items) >= 4:
                break
    return overlays


def progressive_match_is_valid(group_title: str, label: str, text: str, start: int, end: int) -> bool:
    if group_title != "DEDUCT EXPENSES":
        return True
    window = text[max(0, start - 110): min(len(text), end + 150)].lower()
    if label == "MILEAGE":
        return bool(re.search(r"\b(mileage deduction|mileage deductions|qualify for mileage|drove for|ride share|delivery apps?)\b", window))
    if label == "INTERNET":
        return bool(re.search(r"\b(internet bill|phone bill|part of your internet|freelance from home|home.*internet|business expenses?|deduct|deduction|expense)\b", window))
    if label == "SOFTWARE" and re.search(r"\b(assume|trust|handled everything|auto-filled|checking them)\b", window):
        return bool(re.search(r"\b(bought|tools|subscriptions|supplies|expenses|deduct|costs|work)\b", window))
    if label == "SOFTWARE":
        return bool(re.search(r"\b(bought tools|tools, software|software, subscriptions|subscriptions|supplies|related to your work|business expenses?|deduct|expense|costs)\b", window))
    if label == "EQUIPMENT":
        return bool(re.search(r"\b(office setup|equipment.*qualify|equipment.*business|equipment.*expenses|business expenses?|related to your work|deduct|expense)\b", window))
    if label == "HOME OFFICE":
        return bool(re.search(r"\b(home office|workspace|freelance from home|office setup|business expenses?|deduct|expense)\b", window))
    return True


STAT_VALUE_RE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:thousand|million|billion|k))?"
    r"|\b\d+(?:\.\d+)?\s?(?:%|percent)"
    r"|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b",
    re.IGNORECASE,
)


def normalize_stat_value(raw: str) -> str:
    value = clean_text(raw)
    value = re.sub(r"\bpercent\b", "%", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+%", "%", value)
    value = re.sub(r"\$\s+", "$", value)
    value = re.sub(r"\bthousand\b", "K", value, flags=re.IGNORECASE)
    value = re.sub(r"\bmillion\b", "M", value, flags=re.IGNORECASE)
    value = re.sub(r"\bbillion\b", "B", value, flags=re.IGNORECASE)
    return value.replace(" ", "")[:14]


def stat_percent_number(value: str) -> Optional[float]:
    match = re.search(r"(\d+(?:\.\d+)?)\s?%", value)
    if not match:
        return None
    number = float(match.group(1))
    return number if 0 < number <= 100 else None


STAT_HEADLINE_STOP = {
    "the", "and", "that", "with", "from", "this", "there", "your", "about", "into", "because",
    "up", "to", "of", "can", "be", "a", "an", "in", "you", "is", "are", "it", "at", "on", "or",
    "will", "was", "were", "over", "just", "only", "for", "by", "get", "put",
    "dollar", "dollars", "percent", "bucks",
}


def stat_headline(sentence: str, fallback: str = "THE REAL NUMBER") -> str:
    words = re.findall(r"[A-Za-z0-9%$]+(?:[-'][A-Za-z0-9%$]+)?", sentence)
    useful = [w for w in words if w.lower() not in STAT_HEADLINE_STOP]
    headline = " ".join(useful[:5]).upper()
    return headline[:60] or fallback


def data_viz_overlays(
    transcript: str,
    duration: float,
    transcript_chunks: List[TranscriptChunk],
) -> List[Dict[str, Any]]:
    """Turn real dollar/percent figures spoken in the transcript into animated
    stat_counter / donut_chart cards. Never invents numbers."""
    chunks = transcript_chunks or approximate_transcript_chunks(transcript, duration, target_seconds=7.0)
    if not chunks:
        return []
    overlays: List[Dict[str, Any]] = []
    seen_values: set[str] = set()
    last_time = -999.0
    for chunk in chunks:
        if chunk.start < 9.0 or chunk.start > duration - 6.0:
            continue
        for match in STAT_VALUE_RE.finditer(chunk.text):
            raw_value = match.group(0)
            # Skip bare years and small counting numbers with no unit.
            if not re.search(r"[$%]|percent|thousand|million|billion|,", raw_value, re.IGNORECASE):
                continue
            value = normalize_stat_value(raw_value)
            if not value or value in seen_values:
                continue
            trailing = chunk.text[match.end(): match.end() + 9].lower()
            if "$" not in value and "%" not in value and trailing.lstrip().startswith(("dollar", "buck")):
                value = f"${value}"
            relative = match.start() / max(1, len(chunk.text))
            start = clamp_float(chunk.start + relative * max(0.2, chunk.end - chunk.start), 9.0, duration - 6.0)
            if start - last_time < 22.0:
                continue
            sentence_start = chunk.text.rfind(".", 0, match.start()) + 1
            sentence_end = chunk.text.find(".", match.end())
            if sentence_end == -1:
                sentence_end = min(len(chunk.text), match.end() + 160)
            sentence = chunk.text[sentence_start:sentence_end]
            headline = stat_headline(re.sub(re.escape(raw_value), "", sentence, flags=re.IGNORECASE))
            percent = stat_percent_number(value)
            overlays.append(
                {
                    "kind": "donut_chart" if percent is not None else "stat_counter",
                    "time": round(start + 0.4, 2),
                    "duration": 4.6,
                    "text": headline,
                    "cue": clean_text(sentence)[:140],
                    "label": "FROM THE SCRIPT",
                    "value": value,
                    "tone": "money",
                    "icon": "dollar",
                    "sfx": "hit",
                }
            )
            seen_values.add(value)
            last_time = start
            break
        if len(overlays) >= 6:
            break
    return overlays


def prioritize_data_viz(overlays: List[Dict[str, Any]], stats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop generic callouts/cards that sit on top of a data visual so the
    number card always wins the slot."""
    stat_times = [float(item.get("time") or 0) for item in stats]
    if not stat_times:
        return overlays
    keep: List[Dict[str, Any]] = []
    for raw in overlays:
        kind = LEGACY_CARD_KIND_MAP.get(str(raw.get("kind") or ""), str(raw.get("kind") or ""))
        timepoint = float(raw.get("time") or 0)
        protected = (
            kind in DATA_VIZ_KINDS
            or kind == "title_card"
            or bool(raw.get("section_turn"))
            or bool(raw.get("progressive"))
            or timepoint < 10
        )
        if not protected and any(abs(timepoint - stat_time) < 4.5 for stat_time in stat_times):
            continue
        keep.append(raw)
    return keep


def remove_conflicting_progressive_cards(
    overlays: List[Dict[str, Any]],
    progressive: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    progressive_titles = {
        re.sub(r"[^a-z0-9]+", "", str(item.get("text") or "").lower())
        for item in progressive
        if item.get("kind") == "checklist_reveal"
    }
    if not progressive_titles:
        return overlays
    clean: List[Dict[str, Any]] = []
    for raw in overlays:
        kind = LEGACY_CARD_KIND_MAP.get(str(raw.get("kind") or ""), str(raw.get("kind") or ""))
        text_key = re.sub(r"[^a-z0-9]+", "", str(raw.get("text") or "").lower())
        if kind == "checklist_reveal" and text_key in progressive_titles and not raw.get("progressive"):
            continue
        clean.append(raw)
    return clean


def is_generic_checklist_card(text: str, label: str, items: List[str]) -> bool:
    text_key = re.sub(r"[^a-z0-9]+", "", text.lower())
    label_key = re.sub(r"[^a-z0-9]+", "", label.lower())
    item_keys = {re.sub(r"[^a-z0-9]+", "", item.lower()) for item in items}
    if text_key in {"verifybeforefiling", "commoncheck", "checkeveryform", "verifybeforefiling"}:
        return True
    if label_key in {"commoncheck", "checkthis", "mistakecheck"} and text_key.startswith(("verify", "check")):
        return True
    generic_items = {"form", "number", "receipt", "deadline", "checktheform", "verifythenumber", "keeptheproof"}
    return bool(item_keys) and item_keys.issubset(generic_items)


def concise_callout_text(text: str, fallback: str = "", max_words: int = 4) -> str:
    raw = clean_text(text or fallback)
    if not raw:
        return clean_text(fallback).upper()
    lower = raw.lower()
    patterns = [
        (r"losing money quietly", "LOSING MONEY QUIETLY"),
        (r"software[^.]{0,45}always[^.]{0,25}right", "SOFTWARE ALWAYS RIGHT"),
        (r"close[^.]{0,25}correct", "CLOSE IS CORRECT"),
        (r"extension[^.]{0,50}pay", "EXTENSION IS NOT PAYMENT"),
        (r"reported income[^.]{0,65}missing?[^.]{0,35}expenses", "INCOME WITHOUT EXPENSES"),
        (r"receipt|proof|invoice|record", "PROOF MATTERS"),
    ]
    for pattern, phrase in patterns:
        if re.search(pattern, lower):
            return phrase
    words = re.findall(r"[A-Za-z0-9%$]+(?:[-'][A-Za-z0-9%$]+)?", raw.upper())
    clean_words: List[str] = []
    for word in words:
        if clean_words and clean_words[-1] == word:
            continue
        clean_words.append(word)
    while len(clean_words) > 1 and clean_words[-1] in set(clean_words[:-1]):
        clean_words.pop()
    return " ".join(clean_words[:max_words])


def has_real_deadline_value(text: str, value: str) -> bool:
    if value and re.search(r"\d|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec", value, flags=re.IGNORECASE):
        return True
    return bool(
        re.search(
            r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
            r"sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}\b|\b\d{1,2}/\d{1,2}\b",
            text,
            flags=re.IGNORECASE,
        )
    )


def infer_card_tone(text: str, kind: str = "") -> str:
    haystack = f"{kind} {text}".lower()
    if re.search(r"\b(deadline|filing|late|date|due)\b", haystack):
        return "deadline"
    if re.search(
        r"\b(refund|deduction|deductions|write[- ]?off|save|money|dollar|cost|overpay|overpaid|"
        r"401k|ira|roth|pension|social security|rmd|withdrawal|nest egg|\$)\b",
        haystack,
    ):
        return "money"
    if re.search(r"\b(irs|audit|penalty|penalties|risk|warning|mistake|mistakes|error)\b", haystack):
        return "audit" if "irs" in haystack or "audit" in haystack else "warning"
    return "neutral"


def card_kind_for_tone(tone: str) -> str:
    if tone == "money":
        return "underline_callout"
    if tone == "deadline":
        return "deadline_flip"
    if tone in {"warning", "audit"}:
        return "mistake_strip"
    return "form_highlight"


def label_for_tone(tone: str) -> str:
    return {
        "money": "LOWER TAXABLE INCOME",
        "deadline": "DEADLINE",
        "warning": "COMMON MISTAKE",
        "audit": "CHECK THIS",
        "neutral": "TAX NOTE",
    }.get(tone, "TAX NOTE")


def checklist_items_for_phrase(phrase: str) -> List[str]:
    words = [word for word in re.findall(r"[A-Za-z0-9%$]+(?:[-'][A-Za-z0-9%$]+)?", phrase) if len(word) > 2]
    if len(words) >= 6:
        return [" ".join(words[:2]), " ".join(words[2:4]), " ".join(words[4:6])]
    return ["Check the form", "Verify the number", "Keep the proof"]


def icon_for_tone(tone: str) -> str:
    return {
        "money": "dollar",
        "deadline": "calendar",
        "warning": "warning",
        "audit": "warning",
        "neutral": "receipt",
    }.get(tone, "receipt")


def extract_overlay_value(text: str) -> str:
    match = re.search(r"\$[\d,]+(?:\.\d+)?|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d+(?:\.\d+)?%", text)
    return match.group(0) if match else ""


def safe_meter(value: Any, tone: str) -> float:
    default = {"money": 0.64, "deadline": 0.72, "warning": 0.78, "audit": 0.84, "neutral": 0.52}.get(tone, 0.52)
    if value is None or value == "":
        return default
    return clamp_float(value, 0, 1)


def sanitize_overlays(overlays: List[Dict[str, Any]], images: List[PlannedImage], duration: float) -> List[Dict[str, Any]]:
    clean: List[Dict[str, Any]] = []
    last_any_time = -999.0
    last_callout_time = -999.0
    last_full_time = -999.0
    seen_text: set[str] = set()
    image_windows = [(image.time - 0.4, image.time + image.duration + 0.8) for image in images]
    for raw in sorted(overlays, key=lambda item: float(item.get("time") or 0)):
        start = clamp_float(raw.get("time"), 0, duration)
        if start < 5.5:
            continue
        kind = str(raw.get("kind") or "form_highlight")
        kind = LEGACY_CARD_KIND_MAP.get(kind, kind)
        raw_text = clean_text(str(raw.get("text") or ""))
        text = headline_from_sentence(raw_text, fallback="")
        label_override = ""
        value_override = ""
        if kind == "title_card":
            text = strip_leading_card_number(text)
            if is_generic_section_title(text):
                continue
        if not text:
            continue
        if kind == "mini_list":
            text = " | ".join(part.strip() for part in re.split(r"[;|•]", str(raw.get("text") or "")) if part.strip()[:48])[:90]
        if kind in {"word_hit", "bottom_text", "side_text", "mini_list"}:
            kind = "checklist_reveal" if kind == "mini_list" else "underline_callout"
        if kind not in SAFE_OVERLAY_KINDS:
            kind = "underline_callout"
        if kind in {"strike_callout", "mistake_strip"}:
            text = concise_callout_text(raw_text, text, 4)
        elif kind in {"underline_callout", "soft_caption"}:
            text = concise_callout_text(raw_text, text, 5)
        if kind == "form_highlight" and re.sub(r"[^a-z0-9]+", "", text.lower()) in {"matchforms", "checkforms"}:
            text = "MATCH EVERY FORM"
            label_override = "TAX FILE"
        chart_data: List[Dict[str, Any]] = []
        if kind in DATA_VIZ_KINDS:
            value_text = normalize_stat_value(str(raw.get("value") or "")) or extract_overlay_value(raw_text)
            raw_data = raw.get("data") if isinstance(raw.get("data"), list) else []
            for entry in raw_data[:5]:
                if not isinstance(entry, dict):
                    continue
                try:
                    entry_value = float(re.sub(r"[^0-9.\-]", "", str(entry.get("value") or "")) or "nan")
                except ValueError:
                    continue
                entry_label = clean_text(str(entry.get("label") or ""))[:26].upper()
                if entry_label and math.isfinite(entry_value):
                    chart_data.append({"label": entry_label, "value": round(entry_value, 2)})
            if kind == "bar_chart" and len(chart_data) < 2:
                kind = "stat_counter" if re.search(r"\d", value_text) else "underline_callout"
            if kind == "donut_chart" and stat_percent_number(value_text) is None:
                kind = "stat_counter" if re.search(r"\d", value_text) else "underline_callout"
            if kind == "stat_counter" and not re.search(r"\d", value_text):
                kind = "underline_callout"
            value_override = value_text
        if kind == "deadline_flip":
            value_override = clean_text(str(raw.get("value") or ""))[:18] or extract_overlay_value(raw_text)
            if not has_real_deadline_value(raw_text, value_override):
                kind = "money_leak"
                lower = raw_text.lower()
                text = "EXTENSION IS NOT PAYMENT" if "extension" in lower and "pay" in lower else "DEADLINES MATTER"
                label_override = "DEADLINE"
                value_override = ""
        is_callout = kind in AVATAR_CALLOUT_KINDS
        is_section_turn = kind == "title_card" and bool(raw.get("section_turn"))
        is_progressive = kind == "checklist_reveal" and bool(raw.get("progressive"))
        duration_range = (2.6, 4.0) if is_callout else ((3.2, 4.6) if is_progressive else (4.0, 5.8))
        candidate_duration = clamp_float(raw.get("duration"), duration_range[0], duration_range[1])
        if kind in DATA_VIZ_KINDS:
            # Data visuals carry real numbers; slide them past image inserts instead of dropping them.
            for lo, hi in sorted(image_windows):
                if start < hi and start + candidate_duration > lo:
                    start = round(hi + 0.6, 2)
            if start + candidate_duration > duration - 1.5:
                continue
        if any(start < hi and start + candidate_duration > lo for lo, hi in image_windows):
            continue
        raw_items = raw.get("items") if isinstance(raw.get("items"), list) else []
        if kind == "checklist_reveal" and is_generic_checklist_card(
            text,
            clean_text(str(raw.get("label") or "")),
            [clean_text(str(item)) for item in raw_items if clean_text(str(item))],
        ):
            continue
        item_key = re.sub(r"[^a-z0-9]+", "", " ".join(str(item) for item in raw_items).lower())[:52]
        text_key = re.sub(r"[^a-z0-9]+", "", text.lower())[:42]
        duplicate_key = f"{text_key}:{item_key}" if is_progressive and item_key else text_key
        if duplicate_key in seen_text:
            continue
        seen_text.add(duplicate_key)
        is_data_viz = kind in DATA_VIZ_KINDS
        min_gap = (
            6.0
            if start < 30
            else (
                6.5
                if is_callout
                else (
                    5.2
                    if is_progressive
                    else (7.0 if is_section_turn else (10.0 if is_data_viz else (12.0 if kind == "title_card" else 16.0)))
                )
            )
        )
        if start - last_any_time < (2.8 if is_section_turn else (3.4 if is_progressive else (3.0 if is_data_viz else 4.2))):
            continue
        if is_callout and start - last_callout_time < min_gap:
            continue
        if not is_callout and start - last_full_time < min_gap:
            continue
        sfx = str(raw.get("sfx") or ("whoosh" if kind in EDITORIAL_CARD_KINDS or kind == "title_card" else "pop"))
        items = [headline_from_sentence(str(item), fallback="").upper()[:44] for item in raw_items if clean_text(str(item))][:4]
        if not items and kind == "checklist_reveal":
            items = [headline_from_sentence(item, fallback="").upper()[:44] for item in checklist_items_for_phrase(text)]
        item: Dict[str, Any] = {
            "kind": kind,
            "time": start,
            "duration": candidate_duration,
            "text": text[:74].upper(),
            "cue": clean_text(str(raw.get("cue") or ""))[:140],
            "number": raw.get("number") if kind == "title_card" and start >= 5.5 else None,
            "accent": "yellow" if kind == "title_card" else "white",
            "sfx": sfx if sfx in {"hit", "pop", "click", "whoosh"} else "click",
        }
        if items:
            item["items"] = items
        if kind in EDITORIAL_CARD_KINDS:
            tone = str(raw.get("tone") or infer_card_tone(raw_text or text, kind))
            if tone not in {"money", "warning", "deadline", "audit", "neutral"}:
                tone = infer_card_tone(raw_text or text, kind)
            icon = str(raw.get("icon") or icon_for_tone(tone))
            if icon not in {"receipt", "warning", "calendar", "dollar", "check"}:
                icon = icon_for_tone(tone)
            item.update(
                {
                    "label": clean_text(str(raw.get("label") or "")).upper()[:24],
                    "value": value_override or clean_text(str(raw.get("value") or ""))[:18] or extract_overlay_value(raw_text),
                    "meter": safe_meter(raw.get("meter"), tone),
                    "tone": tone,
                    "icon": icon,
                    "duration": candidate_duration,
                    "sfx": item["sfx"] if item["sfx"] != "click" else "whoosh",
                }
            )
            if label_override:
                item["label"] = label_override
        elif kind in DATA_VIZ_KINDS:
            tone = str(raw.get("tone") or infer_card_tone(raw_text or text, kind))
            if tone not in {"money", "warning", "deadline", "audit", "neutral"}:
                tone = infer_card_tone(raw_text or text, kind)
            item.update(
                {
                    "label": (label_override or clean_text(str(raw.get("label") or label_for_tone(tone))).upper())[:24],
                    "value": value_override[:18],
                    "tone": tone,
                    "icon": icon_for_tone(tone),
                    "sfx": item["sfx"] if item["sfx"] != "click" else "hit",
                }
            )
            if chart_data:
                item["data"] = chart_data
        elif kind in AVATAR_CALLOUT_KINDS:
            tone = str(raw.get("tone") or infer_card_tone(raw_text or text, kind))
            if tone not in {"money", "warning", "deadline", "audit", "neutral"}:
                tone = infer_card_tone(raw_text or text, kind)
            item.update(
                {
                    "label": (label_override or clean_text(str(raw.get("label") or label_for_tone(tone))).upper())[:24],
                    "value": clean_text(str(raw.get("value") or ""))[:18] or extract_overlay_value(raw_text),
                    "tone": tone,
                    "icon": icon_for_tone(tone),
                }
            )
        if is_progressive:
            item["progressive"] = True
        if is_section_turn:
            item["section_turn"] = True
        clean.append(item)
        last_any_time = start
        if is_callout:
            last_callout_time = start
        else:
            last_full_time = start
    return clean


def normalize_zoom_density(raw_zooms: List[Dict[str, Any]], duration: float) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []
    prev_scale = 1.0
    prev_x = 0.0
    prev_y = 0.0
    for raw in sorted(raw_zooms, key=lambda item: float(item.get("start") or 0)):
        start = clamp_float(raw.get("start"), 0, duration)
        end = clamp_float(raw.get("end"), start + 0.8, duration)
        if end <= start:
            continue
        mode = str(raw.get("mode") or ("punch" if end - start < 2.2 or float(raw.get("scale") or 1) > 1.14 else "slow"))
        scale = clamp_float(raw.get("scale"), 1.0, 1.24 if mode in {"flash", "punch"} else 1.16)
        cleaned.append(
            {
                "start": start,
                "end": end,
                "fromScale": clamp_float(raw.get("fromScale"), 1.0, 1.24) if raw.get("fromScale") is not None else round(prev_scale, 3),
                "fromX": clamp_float(raw.get("fromX"), -7, 7) if raw.get("fromX") is not None else round(prev_x, 3),
                "fromY": clamp_float(raw.get("fromY"), -5, 5) if raw.get("fromY") is not None else round(prev_y, 3),
                "scale": scale,
                "x": clamp_float(raw.get("x"), -7, 7),
                "y": clamp_float(raw.get("y"), -5, 5),
                "mode": mode if mode in {"flash", "punch", "slow", "steady", "settle"} else "slow",
            }
        )
        prev_scale = scale
        prev_x = float(cleaned[-1]["x"])
        prev_y = float(cleaned[-1]["y"])

    filled: List[Dict[str, Any]] = []
    cursor = 0.0
    previous_scale = 1.0
    for zoom in cleaned:
        start = float(zoom["start"])
        if start > cursor + (6.0 if cursor < 30 else 12.0):
            filled.extend(generated_zoom_segments(cursor, start, previous_scale))
        filled.append(zoom)
        cursor = max(cursor, float(zoom["end"]))
        previous_scale = float(zoom["scale"])
    if cursor < duration:
        filled.extend(generated_zoom_segments(cursor, duration, previous_scale))
    return filled


def normalize_images(
    images: List[PlannedImage],
    title: str,
    transcript: str,
    duration: float,
    image_target: int,
    fill_missing: bool = True,
) -> List[PlannedImage]:
    unique: List[PlannedImage] = []
    seen: set[str] = set()
    for image in sorted(images, key=lambda item: item.time):
        key = re.sub(r"[^a-z0-9]+", "", image.query.lower())[:44]
        if not key or key in seen:
            continue
        seen.add(key)
        image.query = clean_image_query(image.query)
        image.caption = headline_from_sentence(image.caption or image.query, fallback=title)
        image.time = clamp_float(image.time, 3, max(3, duration - 3))
        image.duration = clamp_float(image.duration, 4.5, 6.8)
        unique.append(image)

    if fill_missing and len(unique) < image_target:
        seeds = image_seed_phrases(title, transcript, image_target * 2) + fallback_image_phrases(title)
        first_time = 24 if duration > 75 else 8
        usable_span = max(12, duration - first_time - 7)
        for seed in seeds:
            if len(unique) >= image_target:
                break
            phrase = headline_from_sentence(seed, fallback=title)
            query = clean_image_query(seed)
            key = re.sub(r"[^a-z0-9]+", "", query.lower())[:44]
            if key in seen:
                continue
            seen.add(key)
            i = len(unique)
            t = min(duration - 6, first_time + (i + 0.6) * usable_span / max(1, image_target))
            unique.append(
                PlannedImage(
                    index=i + 1,
                    time=round(t, 2),
                    duration=5.2,
                    query=query,
                    caption=phrase,
                    cue=clean_text(seed)[:140],
                )
            )

    trimmed = enforce_image_spacing(unique[:image_target], duration)
    for i, image in enumerate(trimmed, start=1):
        image.index = i
    return trimmed


def enforce_image_spacing(images: List[PlannedImage], duration: float) -> List[PlannedImage]:
    spaced: List[PlannedImage] = []
    last_end = -999.0
    for image in sorted(images, key=lambda item: item.time):
        latest_start = max(3.0, duration - image.duration - 2.0)
        desired = max(image.time, last_end + IMAGE_BREATHING_ROOM_SECONDS)
        if desired > latest_start:
            continue
        image.time = round(desired, 2)
        spaced.append(image)
        last_end = image.time + image.duration
    return spaced


def parse_json_object(text: str) -> Dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object returned.")
    return json.loads(match.group(0))


def ai_director_plan(
    provider: str,
    model: str,
    title: str,
    transcript: str,
    duration: float,
    image_target: int,
    log: Any,
    transcript_chunks: Optional[List[TranscriptChunk]] = None,
    title_is_user_supplied: bool = False,
) -> DirectorPlan:
    client = client_for(provider)
    if client is None:
        raise RuntimeError(f"{PLANNING_PROVIDER_LABELS.get(provider, provider)} is not configured.")

    timed_chunks = transcript_chunks or approximate_transcript_chunks(transcript, duration)
    timed_transcript = transcript_chunks_for_prompt(timed_chunks, duration)
    clipped = timed_transcript or transcript[:18000]
    system = (
        "You are a senior YouTube retention editor for clean educational tax and retirement talking-head videos "
        "(topics like 401k, IRA, Roth, RMDs, Social Security, pensions, deductions, filing). "
        "Build a precise edit decision list from timestamped transcript segments. "
        "Use the avatar as the base, then layer purposeful full-screen editorial cards, animated data visuals "
        "(stat counters, bar charts, donut charts) for every real number in the script, frequent short text callouts, "
        "and B-roll image inserts. "
        "Avoid random motion, center-face text, green text, subtitles, crowded overlays, and generic decoration. "
        "Do not copy any creator branding. Return valid JSON only."
    )
    user = f"""
Title source: {"user supplied" if title_is_user_supplied else "infer from transcript"}
Working title: {title if title_is_user_supplied else "AUTO_TITLE"}
Duration seconds: {duration:.2f}
Timestamped transcript chunks:
{clipped}

Return JSON with this exact shape:
{{
  "title": "short display title",
  "segments": [
    {{
      "number": 1,
      "start": 0,
      "end": 52,
      "role": "hook|mistake|rule|example|deadline|money|action|recap",
      "summary": "what this segment is doing",
      "edit": "avatar|card|image|avatar_with_card",
      "card": {{
        "kind": "soft_caption|underline_callout|strike_callout|mistake_strip|form_highlight|receipt_stack|rule_slate|deadline_flip|money_leak|checklist_reveal|document_scan|title_card",
        "time": 6.4,
        "duration": 2.7,
        "text": "short headline",
        "label": "optional short label",
        "value": "only if the transcript says a real number",
        "items": ["optional short item", "optional short item"],
        "tone": "money|warning|deadline|audit|neutral",
        "number": 1,
        "progressive": true
      }},
      "image": {{"time": 44, "duration": 5.2, "query": "specific real-photo search query", "caption": "short caption"}}
    }}
  ],
  "chapters": [{{"number": 1, "start": 6, "end": 80, "title": "major section title"}}],
  "overlays": [
    {{"kind": "soft_caption|underline_callout|strike_callout|mistake_strip|form_highlight|receipt_stack|rule_slate|deadline_flip|money_leak|checklist_reveal|document_scan|title_card|stat_counter|bar_chart|donut_chart", "time": 6.4, "duration": 3.0, "text": "short text", "cue": "exact words copied verbatim from the transcript at this moment", "value": "$1200 or 30% if transcript says it", "label": "short label", "items": ["optional", "optional"], "data": [{{"label": "401K", "value": 23000}}, {{"label": "IRA", "value": 7000}}], "meter": 0.65, "icon": "receipt|warning|calendar|dollar|check", "tone": "money|warning|deadline|audit|neutral", "number": 1, "progressive": true, "accent": "yellow|white", "sfx": "hit|pop|click|whoosh"}}
  ],
  "zooms": [
    {{"start": 0, "end": 5, "scale": 1.08, "x": 0, "y": 0, "mode": "flash|punch|slow|steady|settle"}}
  ],
  "images": [
    {{"time": 45, "duration": 5.2, "query": "specific search query for useful B-roll image", "caption": "short caption", "cue": "exact words copied verbatim from the transcript at this moment"}}
  ]
}}

Rules:
- If Title source is "infer from transcript", create a clean display title from the transcript. Never use AUTO_TITLE,
  file names, test names, or raw video filenames as the title.
- If the user supplied a title, use it unless the transcript makes it obviously wrong.
- The first 5-7 seconds must be avatar only. No title card, no image, no text overlay at frame 0.
- Right after the first real punchline, usually between 5.8 and 8.0 seconds, place one clean centered
  full-screen money_leak impact card. Use label "TAX MISTAKES" and one short 2-4 word headline such as
  "LOSING MONEY QUIETLY", "TAX MISTAKES COST", or another transcript-specific hook.
- First 30 seconds are the hook: use deliberate punch-ins, the one early impact card, and 1-2 small avatar
  callouts. Do not put text over the speaker's face.
- After 30 seconds, use mostly slower push-ins with occasional punch-ins on important words, numbers, warnings,
  or turns in the argument.
- Use numbered title_card only for true major sections, roughly every 70-120 seconds. Do not number every visual beat.
- Always identify the transcript's big teaching bullets and section turns before choosing overlays.
  Phrases like "start with...", "that brings us to the second mistake", "the final mistake is...",
  "now check...", or "deadlines matter" are section-turn signals. Put a clean numbered title_card at the
  start of the section, with the card text naming the actual topic, not the transition phrase.
  Example: if the speaker says "That brings us to the second mistake. Forgetting deductible expenses.",
  use title_card number 2 with text "DEDUCTIBLE EXPENSES".
  Example: if the speaker says "The final mistake is thinking this only applies to business owners.",
  use title_card with text "NOT JUST BUSINESS OWNERS".
- Never use generic title_card text like "SECOND MISTAKE", "THIRD MISTAKE", "FINAL MISTAKE", or
  "MISTAKE 2". Wait for the topic sentence and name the card after the topic.
- If a title_card uses number: 1, 2, etc., do not repeat that number in the text. Text should be "HIDDEN TAXABLE INCOME",
  not "1 HIDDEN TAXABLE INCOME".
- Use small avatar callouts often enough to add motion: underline_callout for one or two important words, strike_callout
  when correcting a bad assumption, soft_caption for a clean lower-third, and mistake_strip for a quick mistake/fix moment.
- strike_callout and mistake_strip text must be only the false assumption being corrected, 2-4 words max.
  Good style: "SOFTWARE ALWAYS RIGHT", "CLOSE IS CORRECT", "TOO SMALL TO REPORT".
  Never use a full sentence, never repeat words, and never place crossed text over an image insert.
- Do not use banner text over the avatar face. Do not create subtitle-like text.
- Full-screen editorial cards should be rare and clean. Prefer money_leak for centered impact pages,
  form_highlight for rule/deduction moments, checklist_reveal only for real multi-item sequences, and title_card
  for section breaks. Avoid heavy black panels.
- For list/explanation sequences such as mileage, internet, software, equipment, forms, deadlines, or multiple examples:
  do not show all items at once for one short moment. Make the card return at each relevant transcript timestamp.
  Example pattern: checklist_reveal "DEDUCT EXPENSES" with items ["MILEAGE"] when mileage starts, then later
  checklist_reveal "DEDUCT EXPENSES" with items ["MILEAGE", "INTERNET"] when internet starts, then later the same
  card with the next cumulative item. Set progressive: true for these returning cards.
- For progressive cards, keep items in the exact spoken order from the transcript. Do not sort them by importance.
- Do not create generic "VERIFY BEFORE FILING", "COMMON CHECK", "CHECK FORM", or "VERIFY NUMBER" checklist cards.
  If the transcript needs that idea, use a short avatar strike/underline callout instead.
- Use form/document cards only when they explain a useful viewer action. "MATCH FORMS" alone is too vague; prefer
  "MATCH EVERY FORM" with useful items such as W-2, 1099, deductions, credits if the transcript says those.
- Use deadline_flip only if the transcript gives a real date, due date, deadline value, or specific calendar moment.
  If it only says deadlines matter or extension-to-file is not extension-to-pay, use a clean money_leak or underline_callout
  with text such as "EXTENSION IS NOT PAYMENT" instead of a calendar.
- Do not make a "DEDUCT EXPENSES" card just because the word software appears. Only count software as a deduction item
  when the transcript is discussing bought tools, subscriptions, supplies, work expenses, business expenses, or deductions.
  If the transcript says people trusted software or software handled everything, that is a mistake/cross-out moment,
  not a deduction checklist item.
- SYNC: every overlay and image MUST include "cue": 4-10 words copied VERBATIM from the transcript at the exact
  moment the visual should appear (the words being spoken when it pops). Do not paraphrase the cue - copy the
  transcript words exactly. The renderer aligns each visual to the spoken audio using this cue.
- Add value only when the script actually mentions a number, dollar amount, percent, year, or deadline.
- Do not invent numbers, deadlines, or tax rules.
- DATA VISUALS: every time the transcript states a real number, prefer an animated data visual over plain text.
  Use stat_counter for a single dollar amount or count (value: "$23,000"), donut_chart for a single percentage
  (value: "22%"), and bar_chart when the transcript compares two or more real amounts (fill data with the exact
  spoken labels and numbers, e.g. data: [{{"label": "401K LIMIT", "value": 23000}}, {{"label": "IRA LIMIT", "value": 7000}}]).
  Never chart numbers the speaker did not say. Aim for one data visual whenever a meaningful number appears.
- After the opening, use full-screen cards or data visuals roughly every 25-50 seconds. Between them, keep small
  avatar callouts (underline_callout, soft_caption, strike_callout) coming every 10-18 seconds so the frame is
  never static for long. Every major claim, warning, rule, or number should have a matching visual beat.
- Callouts should last 2.8-3.8 seconds. Full cards and data visuals should last 4.2-5.6 seconds unless they are
  progressive returning checklist beats, which should last 3.2-4.4 seconds. Image inserts should last 4.8-6.5 seconds.
- Use yellow or white accents only. Do not use green.
- Put zoom events continuously from start to finish; use scale 1.02-1.07 for slow/steady and up to 1.10 for rare punch-ins.
- Add about {image_target} image inserts (roughly two per minute). Space them through the video; do not stack them.
- Image queries must describe one concrete photographable subject in 4-8 plain words, e.g.
  "retired couple reviewing finances kitchen table", "social security card with benefit statement",
  "401k statement on desk with calculator". Never use abstract phrases, transcript quotes, boolean operators,
  or words like mistake/rule/concept. Real documentary/editorial photos only, no stock illustrations, thumbnails,
  templates, or text posters.
- No overlay may overlap an image insert. Leave at least 1 second of breathing room before and after images.
- Keep text short and bold. Avoid long sentences.
- Times must be within duration.
"""
    log(f"Planning edit with {PLANNING_PROVIDER_LABELS.get(provider, provider)} ({model})...")
    content = chat_completion_text(
        client,
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.45,
        log=log,
    )
    data = parse_json_object(content)
    return normalize_plan(data, title=title, duration=duration)


TRANSIENT_API_MARKERS = (
    "524",
    "522",
    "502",
    "503",
    "504",
    "timeout",
    "timed out",
    "retryable",
    "overloaded",
    "too many requests",
    "429",
    "connection error",
    "connection reset",
    "remote protocol",
    "incomplete",
)


def transient_api_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in TRANSIENT_API_MARKERS)


def chat_completion_text(
    client: Any,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float,
    log: Any,
    attempts: int = 3,
) -> str:
    """Stream the completion so proxies never see a silent 120s window
    (Cloudflare 524), and auto-retry transient failures with backoff."""
    delay = 15.0
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            try:
                stream = client.chat.completions.create(
                    model=model, messages=messages, temperature=temperature, stream=True
                )
                parts: List[str] = []
                for chunk in stream:
                    if not getattr(chunk, "choices", None):
                        continue
                    delta = chunk.choices[0].delta
                    piece = getattr(delta, "content", None) if delta is not None else None
                    if piece:
                        parts.append(piece)
                text = "".join(parts)
            except Exception as stream_exc:
                # Some OpenAI-compatible gateways reject stream=True; try once plain.
                if "stream" not in str(stream_exc).lower():
                    raise
                response = client.chat.completions.create(model=model, messages=messages, temperature=temperature)
                text = response.choices[0].message.content or ""
            if text.strip():
                return text
            raise RuntimeError("Model returned an empty response.")
        except Exception as exc:
            last_exc = exc
            if attempt < attempts and transient_api_error(exc):
                log(
                    f"Planning request stalled (attempt {attempt}/{attempts}): "
                    f"{brief_error(exc, 140)} Retrying in {delay:.0f}s..."
                )
                time.sleep(delay)
                delay = min(delay * 2.5, 120.0)
                continue
            raise
    raise last_exc if last_exc else RuntimeError("Planning request failed.")


def planning_batch_count(duration: float) -> int:
    # Smaller windows keep each request fast enough to stay well under
    # gateway timeouts (Cloudflare cuts silent responses at 120s).
    if duration < 5 * 60:
        return 1
    if duration < 9 * 60:
        return 2
    return min(8, max(3, math.ceil(duration / (4 * 60))))


def split_transcript_batches(
    transcript: str,
    transcript_chunks: List[TranscriptChunk],
    duration: float,
    batch_count: int,
) -> List[Tuple[float, float, List[TranscriptChunk], str]]:
    chunks = transcript_chunks or approximate_transcript_chunks(transcript, duration, target_seconds=7.0)
    if not chunks:
        return [(0.0, duration, [], transcript)]

    batches: List[Tuple[float, float, List[TranscriptChunk], str]] = []
    step = duration / max(1, batch_count)
    for i in range(batch_count):
        start = i * step
        end = duration if i == batch_count - 1 else (i + 1) * step
        part_chunks = [chunk for chunk in chunks if chunk.end >= start - 0.2 and chunk.start <= end + 0.2]
        part_text = clean_text(" ".join(chunk.text for chunk in part_chunks))
        if part_chunks and part_text:
            batches.append((start, end, part_chunks, part_text))
    return batches or [(0.0, duration, chunks, transcript)]


def filter_plan_to_window(plan: DirectorPlan, start: float, end: float, first_batch: bool) -> DirectorPlan:
    low = 0.0 if first_batch else max(0.0, start - 2.0)
    high = min(plan.duration, end + 4.0)
    plan.chapters = [item for item in plan.chapters if low <= float(item.get("start") or 0) <= high]
    plan.overlays = [item for item in plan.overlays if low <= float(item.get("time") or 0) <= high]
    plan.zooms = [item for item in plan.zooms if low <= float(item.get("start") or 0) <= high]
    plan.images = [item for item in plan.images if low <= item.time <= high]
    plan.segments = [item for item in plan.segments if low <= float(item.get("start") or 0) <= high]
    return plan


def merge_director_plans(parts: List[DirectorPlan], fallback_title: str, duration: float) -> DirectorPlan:
    merged = DirectorPlan(title=fallback_title, duration=duration)
    for part in parts:
        if part.title and not title_key(part.title) in {"autotitle", "title", "untitled"}:
            merged.title = part.title
            break
    for part in parts:
        merged.chapters.extend(part.chapters)
        merged.overlays.extend(part.overlays)
        merged.zooms.extend(part.zooms)
        merged.images.extend(part.images)
        merged.segments.extend(part.segments)
    merged.chapters.sort(key=lambda item: float(item.get("start") or 0))
    merged.overlays.sort(key=lambda item: float(item.get("time") or 0))
    merged.zooms.sort(key=lambda item: float(item.get("start") or 0))
    merged.images.sort(key=lambda item: item.time)
    for i, image in enumerate(merged.images, start=1):
        image.index = i
    return merged


def ai_director_plan_batched(
    provider: str,
    model: str,
    title: str,
    transcript: str,
    duration: float,
    image_target: int,
    log: Any,
    transcript_chunks: Optional[List[TranscriptChunk]] = None,
    title_is_user_supplied: bool = False,
) -> DirectorPlan:
    batch_count = planning_batch_count(duration)
    if batch_count <= 1:
        return ai_director_plan(
            provider,
            model,
            title,
            transcript,
            duration,
            image_target,
            log,
            transcript_chunks=transcript_chunks,
            title_is_user_supplied=title_is_user_supplied,
        )

    log(f"Planning edit with {PLANNING_PROVIDER_LABELS.get(provider, provider)} ({model}) in {batch_count} batches...")
    batches = split_transcript_batches(transcript, transcript_chunks or [], duration, batch_count)
    parts: List[DirectorPlan] = []
    for i, (start, end, part_chunks, part_text) in enumerate(batches, start=1):
        batch_span = max(1.0, end - start)
        batch_image_target = max(1, round(image_target * batch_span / max(1.0, duration)))
        log(f"Planning batch {i}/{len(batches)} ({start / 60:.1f}-{end / 60:.1f} min)...")
        try:
            part = ai_director_plan(
                provider,
                model,
                title,
                part_text,
                duration,
                batch_image_target,
                log,
                transcript_chunks=part_chunks,
                title_is_user_supplied=title_is_user_supplied,
            )
        except Exception as exc:
            if recoverable_api_error(exc):
                raise
            log(f"Planning batch {i} failed; using local fallback for this section. Reason: {brief_error(exc, 260)}")
            part = local_plan(title, part_text, duration, image_target=batch_image_target)
        parts.append(filter_plan_to_window(part, start, end, first_batch=i == 1))
    return merge_director_plans(parts, title, duration)


def normalize_plan(data: Dict[str, Any], title: str, duration: float) -> DirectorPlan:
    returned_title = clean_text(str(data.get("title") or ""))
    if not returned_title or title_key(returned_title) in {"autotitle", "title", "untitled"}:
        returned_title = title
    plan = DirectorPlan(title=returned_title, duration=duration)
    for i, raw in enumerate(data.get("chapters") or [], start=1):
        start = clamp_float(raw.get("start"), 0, duration)
        end = clamp_float(raw.get("end"), start + 8, duration)
        plan.chapters.append(
            {
                "number": int(raw.get("number") or i),
                "start": start,
                "end": end,
                "title": clean_text(str(raw.get("title") or f"Point {i}"))[:80],
            }
        )
    for i, raw_segment in enumerate(data.get("segments") or [], start=1):
        if not isinstance(raw_segment, dict):
            continue
        seg_start = clamp_float(raw_segment.get("start"), 0, duration)
        seg_end = clamp_float(raw_segment.get("end"), seg_start + 8, duration)
        seg_title = clean_text(str(raw_segment.get("summary") or raw_segment.get("title") or f"Segment {i}"))[:90]
        plan.segments.append(
            {
                "number": int(raw_segment.get("number") or i),
                "start": seg_start,
                "end": seg_end,
                "role": clean_text(str(raw_segment.get("role") or ""))[:24],
                "summary": seg_title,
            }
        )
        if not plan.chapters and i == 1:
            plan.chapters.append({"number": 1, "start": max(5.5, seg_start), "end": seg_end, "title": seg_title})
        card = raw_segment.get("card") if isinstance(raw_segment.get("card"), dict) else None
        if card and clean_text(str(card.get("text") or "")):
            card_time = clamp_float(card.get("time"), max(5.8, seg_start + 0.4), max(5.8, duration - 1.5))
            plan.overlays.append(
                {
                    "kind": str(card.get("kind") or "form_highlight"),
                    "time": card_time,
                    "duration": clamp_float(card.get("duration"), 2.0, 4.2),
                    "text": clean_text(str(card.get("text") or ""))[:110],
                    "value": clean_text(str(card.get("value") or ""))[:24],
                    "label": clean_text(str(card.get("label") or ""))[:32],
                    "items": card.get("items") if isinstance(card.get("items"), list) else [],
                    "data": card.get("data") if isinstance(card.get("data"), list) else [],
                    "cue": clean_text(str(card.get("cue") or ""))[:140],
                    "meter": card.get("meter"),
                    "icon": str(card.get("icon") or ""),
                    "tone": str(card.get("tone") or infer_card_tone(str(card.get("text") or ""), str(card.get("kind") or ""))),
                    "number": card.get("number"),
                    "progressive": bool(card.get("progressive")),
                    "accent": str(card.get("accent") or "yellow"),
                    "sfx": str(card.get("sfx") or "whoosh"),
                }
            )
        image = raw_segment.get("image") if isinstance(raw_segment.get("image"), dict) else None
        if image and clean_text(str(image.get("query") or "")):
            image_time = clamp_float(image.get("time"), max(8, seg_start + 1.0), max(8, duration - 3))
            plan.images.append(
                PlannedImage(
                    index=len(plan.images) + 1,
                    time=image_time,
                    duration=clamp_float(image.get("duration"), 4.8, 6.8),
                    query=clean_image_query(str(image.get("query") or "")[:120]),
                    caption=clean_text(str(image.get("caption") or image.get("query") or ""))[:80],
                    cue=clean_text(str(image.get("cue") or ""))[:140],
                )
            )
    for raw in data.get("overlays") or []:
        start = clamp_float(raw.get("time"), 0, duration)
        dur = clamp_float(raw.get("duration"), 1.2, 5.5)
        text = clean_text(str(raw.get("text") or ""))
        if not text:
            continue
        plan.overlays.append(
            {
                "kind": str(raw.get("kind") or "form_highlight"),
                "time": start,
                "duration": min(dur, max(1.0, duration - start)),
                "text": text[:110],
                "value": clean_text(str(raw.get("value") or ""))[:24],
                "label": clean_text(str(raw.get("label") or ""))[:32],
                "items": raw.get("items") if isinstance(raw.get("items"), list) else [],
                "data": raw.get("data") if isinstance(raw.get("data"), list) else [],
                "cue": clean_text(str(raw.get("cue") or ""))[:140],
                "meter": raw.get("meter"),
                "icon": str(raw.get("icon") or ""),
                "tone": str(raw.get("tone") or ""),
                "number": raw.get("number"),
                "progressive": bool(raw.get("progressive")),
                "accent": str(raw.get("accent") or "yellow"),
                "sfx": str(raw.get("sfx") or "pop"),
            }
        )
    for raw in data.get("zooms") or []:
        start = clamp_float(raw.get("start"), 0, duration)
        end = clamp_float(raw.get("end"), start + 2, duration)
        if end <= start:
            continue
        plan.zooms.append(
            {
                "start": start,
                "end": end,
                "fromScale": clamp_float(raw.get("fromScale"), 1.0, 1.24) if raw.get("fromScale") is not None else None,
                "scale": clamp_float(raw.get("scale"), 1.0, 1.24),
                "x": clamp_float(raw.get("x"), -6, 6),
                "y": clamp_float(raw.get("y"), -4, 4),
                "mode": str(raw.get("mode") or "slow"),
            }
        )
    for i, raw in enumerate(data.get("images") or [], start=1):
        start = clamp_float(raw.get("time"), 3, max(3, duration - 3))
        query = clean_text(str(raw.get("query") or ""))
        if not query:
            continue
        plan.images.append(
            PlannedImage(
                index=i,
                time=start,
                duration=clamp_float(raw.get("duration"), 4.8, 6.8),
                query=clean_image_query(query[:120]),
                caption=clean_text(str(raw.get("caption") or query))[:80],
                cue=clean_text(str(raw.get("cue") or ""))[:140],
            )
        )
    if not plan.zooms:
        plan.zooms = local_plan(title, "", duration).zooms
    return plan


def clamp_float(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except Exception:
        number = low
    return round(max(low, min(high, number)), 3)


def domain_from_image(item: Dict[str, Any]) -> str:
    for key in ("domain", "source", "link", "imageUrl"):
        val = str(item.get(key) or "")
        if not val:
            continue
        if val.startswith("http"):
            return urlparse(val).netloc.lower().replace("www.", "")
        if "." in val and "/" not in val:
            return val.lower().replace("www.", "")
    return ""


def image_sort_key(item: Dict[str, Any]) -> tuple[int, int]:
    width = int(item.get("imageWidth") or 0)
    height = int(item.get("imageHeight") or 0)
    ratio = width / height if width and height else 0
    ideal_ratio_bonus = 120000 if 1.45 <= ratio <= 1.85 else 0
    landscape_bonus = 60000 if MIN_IMAGE_RATIO <= ratio <= MAX_IMAGE_RATIO else 0
    return ideal_ratio_bonus + landscape_bonus + width, height


def has_bad_image_terms(*values: str) -> bool:
    haystack = " ".join(v.lower() for v in values if v)
    return any(term in haystack for term in BAD_IMAGE_TERMS)


def inspect_avatar_image_file(path: Path) -> tuple[bool, int, List[str]]:
    notes: List[str] = []
    score = 100
    try:
        with Image.open(path) as img:
            width, height = img.size
            ratio = width / height if height else 0
            if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT:
                return False, 0, [f"too small {width}x{height}"]
            if not (MIN_IMAGE_RATIO <= ratio <= MAX_IMAGE_RATIO):
                return False, 0, [f"not landscape {ratio:.2f}:1"]
            if img.mode in {"RGBA", "LA"}:
                notes.append("transparent")
                score -= 10

            sample = ImageOps.grayscale(img.convert("RGB").resize((320, 180)))
            edges = sample.filter(ImageFilter.FIND_EDGES)
            edge_values = list(edges.getdata())
            edge_density = sum(1 for px in edge_values if px > 62) / len(edge_values)
            if edge_density > MAX_TEXT_EDGE_DENSITY:
                return False, 0, [f"likely text-heavy thumbnail {edge_density:.2f}"]
            if edge_density > 0.27:
                notes.append("busy/text possible")
                score -= 12

            ratio_distance = abs(ratio - (16 / 9))
            score -= int(ratio_distance * 20)
            if width >= 1400:
                score += 8
            if width >= 1900:
                score += 8
            return True, max(0, min(score, 120)), notes
    except Exception as exc:
        return False, 0, [f"invalid image: {exc}"]


def search_serper_images(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    key = os.getenv("SERPER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("SERPER_API_KEY is missing.")
    response = requests.post(
        SERPER_ENDPOINT,
        headers={"X-API-KEY": key, "Content-Type": "application/json"},
        json={"q": clean_image_query(query), "num": limit, "tbs": "itp:photo"},
        timeout=35,
    )
    response.raise_for_status()
    items = list((response.json() or {}).get("images") or [])
    filtered: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        url = str(item.get("imageUrl") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        domain = domain_from_image(item)
        if blocked_image_domain(domain):
            continue
        if has_bad_image_terms(url, str(item.get("title") or ""), str(item.get("source") or ""), str(item.get("link") or "")):
            continue
        width = int(item.get("imageWidth") or 0)
        height = int(item.get("imageHeight") or 0)
        if width and height:
            ratio = width / height if height else 0
            if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT:
                continue
            if not (MIN_IMAGE_RATIO <= ratio <= MAX_IMAGE_RATIO):
                continue
        filtered.append(item)
    filtered.sort(key=image_sort_key, reverse=True)
    return filtered


def blocked_image_domain(domain_or_source: str) -> bool:
    value = domain_or_source.lower()
    return any(blocked in value for blocked in BLOCKED_IMAGE_DOMAINS)


def download_good_image_choices(
    items: List[Dict[str, Any]],
    dest: Path,
    index: int,
    limit: int = IMAGE_CHOICE_COUNT,
    used_urls: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    dest.mkdir(parents=True, exist_ok=True)
    choices: List[Dict[str, Any]] = []
    used_urls = used_urls if used_urls is not None else set()
    for item in items:
        if len(choices) >= limit:
            break
        url = str(item.get("imageUrl") or "")
        if not url or url in used_urls:
            continue
        domain = domain_from_image(item) or urlparse(url).netloc.lower()
        source = str(item.get("source") or item.get("title") or "").lower()
        if blocked_image_domain(domain) or blocked_image_domain(source):
            continue
        title = str(item.get("title") or "").lower()
        if has_bad_image_terms(url, title, source, str(item.get("link") or "")):
            continue
        width = int(item.get("imageWidth") or 0)
        height = int(item.get("imageHeight") or 0)
        if width and height:
            ratio = width / max(1, height)
            if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT or ratio < MIN_IMAGE_RATIO or ratio > MAX_IMAGE_RATIO:
                continue
        try:
            res = requests.get(url, headers=DOWNLOAD_HEADERS, timeout=25)
            res.raise_for_status()
            content_type = res.headers.get("Content-Type", "")
            if "image" not in content_type.lower():
                continue
            ext = extension_for_image(url, content_type)
            path = dest / f"insert_{index:02d}_{len(choices) + 1}{ext}"
            path.write_bytes(res.content)
            if path.stat().st_size < 3000:
                path.unlink(missing_ok=True)
                continue
            ok, score, notes = inspect_avatar_image_file(path)
            if not ok:
                path.unlink(missing_ok=True)
                continue
            with Image.open(path) as img:
                w, h = img.size
            used_urls.add(url)
            choices.append(
                {
                    "path": path,
                    "source": domain,
                    "width": w,
                    "height": h,
                    "url": url,
                    "quality_score": score,
                    "quality_notes": notes,
                }
            )
        except Exception:
            continue
    choices.sort(key=lambda choice: int(choice.get("quality_score") or 0), reverse=True)
    return choices


def extension_for_image(url: str, content_type: str) -> str:
    if content_type:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if ext == ".jpe":
            return ".jpg"
        if ext in {".jpg", ".jpeg", ".png", ".webp"}:
            return ".jpg" if ext == ".jpeg" else ext
    lower = urlparse(url).path.lower()
    for ext in IMAGE_EXTENSIONS:
        if lower.endswith(ext):
            return ext
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    return ".jpg"


def generate_sfx_files(sfx_dir: Path) -> Dict[str, str]:
    sfx_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "pop": sfx_dir / "pop.wav",
        "click": sfx_dir / "click.wav",
        "hit": sfx_dir / "hit.wav",
        "whoosh": sfx_dir / "whoosh.wav",
    }
    make_pop(files["pop"])
    make_click(files["click"])
    make_hit(files["hit"])
    make_whoosh(files["whoosh"])
    return {name: f"sfx/{path.name}" for name, path in files.items()}


def write_wav(path: Path, samples: List[float], sample_rate: int = 44100) -> None:
    with wave.open(str(path), "w") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sample_rate)
        data = bytearray()
        for sample in samples:
            sample = max(-1.0, min(1.0, sample))
            data.extend(int(sample * 32767).to_bytes(2, "little", signed=True))
        fh.writeframes(bytes(data))


def _one_pole_lowpass(samples: List[float], sr: int, cutoff: Any) -> List[float]:
    """cutoff may be a fixed Hz value or a callable(sample_index) -> Hz for sweeps."""
    out: List[float] = []
    y = 0.0
    dt = 1.0 / sr
    fixed = None if callable(cutoff) else max(20.0, float(cutoff))
    for i, x in enumerate(samples):
        fc = fixed if fixed is not None else max(20.0, float(cutoff(i)))
        rc = 1.0 / (2 * math.pi * fc)
        alpha = dt / (rc + dt)
        y += alpha * (x - y)
        out.append(y)
    return out


def _one_pole_highpass(samples: List[float], sr: int, cutoff: float) -> List[float]:
    low = _one_pole_lowpass(samples, sr, cutoff)
    return [x - l for x, l in zip(samples, low)]


def _bandpass(samples: List[float], sr: int, low_hz: float, high_hz: Any) -> List[float]:
    """high_hz may be a callable(sample_index) -> Hz for swept bands."""
    return _one_pole_lowpass(_one_pole_highpass(samples, sr, low_hz), sr, high_hz)


def _soft_clip(samples: List[float], drive: float = 1.6) -> List[float]:
    norm = math.tanh(drive)
    return [math.tanh(x * drive) / norm for x in samples]


def _normalize(samples: List[float], peak: float) -> List[float]:
    top = max((abs(x) for x in samples), default=0.0)
    if top <= 0:
        return samples
    gain = peak / top
    return [x * gain for x in samples]


def _fade_edges(samples: List[float], sr: int, attack: float = 0.002, release: float = 0.02) -> List[float]:
    n = len(samples)
    a = max(1, int(sr * attack))
    r = max(1, int(sr * release))
    out = list(samples)
    for i in range(min(a, n)):
        out[i] *= i / a
    for i in range(min(r, n)):
        out[n - 1 - i] *= i / r
    return out


def make_pop(path: Path) -> None:
    """Soft, rounded bubble pop: pitch-dropping sine body + tiny airy transient."""
    sr = 44100
    length = int(sr * 0.22)
    rng = random.Random(41)
    body: List[float] = []
    phase = 0.0
    for i in range(length):
        t = i / sr
        freq = 150 + 480 * math.exp(-t * 34)
        phase += 2 * math.pi * freq / sr
        env = (min(1.0, t / 0.004)) * math.exp(-t * 24)
        body.append(math.sin(phase) * env)
    transient = [(rng.random() * 2 - 1) * math.exp(-(i / sr) * 260) for i in range(length)]
    transient = _bandpass(transient, sr, 900, 3400)
    mixed = [b * 0.9 + tr * 0.35 for b, tr in zip(body, transient)]
    write_wav(path, _fade_edges(_normalize(_soft_clip(mixed, 1.4), 0.62), sr), sr)


def make_click(path: Path) -> None:
    """Crisp UI tick: short bright noise burst with a faint wooden body."""
    sr = 44100
    length = int(sr * 0.09)
    rng = random.Random(7)
    noise = [(rng.random() * 2 - 1) * math.exp(-(i / sr) * 320) for i in range(length)]
    tick = _bandpass(noise, sr, 1800, 6500)
    body: List[float] = []
    for i in range(length):
        t = i / sr
        body.append(math.sin(2 * math.pi * 620 * t) * math.exp(-t * 90))
    mixed = [tk * 0.85 + b * 0.3 for tk, b in zip(tick, body)]
    write_wav(path, _fade_edges(_normalize(mixed, 0.5), sr), sr)


def make_hit(path: Path) -> None:
    """Cinematic impact: pitch-dropping sub thump + knock transient + short dark tail."""
    sr = 44100
    length = int(sr * 0.85)
    rng = random.Random(13)

    sub: List[float] = []
    phase = 0.0
    for i in range(length):
        t = i / sr
        freq = 52 + 96 * math.exp(-t * 20)
        phase += 2 * math.pi * freq / sr
        env = (min(1.0, t / 0.003)) * math.exp(-t * 6.5)
        sub.append(math.sin(phase) * env)

    knock = [(rng.random() * 2 - 1) * math.exp(-(i / sr) * 150) for i in range(length)]
    knock = _bandpass(knock, sr, 180, 1200)

    tail = [(rng.random() * 2 - 1) * math.exp(-(i / sr) * 9) * min(1.0, (i / sr) / 0.02) for i in range(length)]
    tail = _one_pole_lowpass(tail, sr, 420)

    mixed = [s * 1.0 + k * 0.5 + tl * 0.12 for s, k, tl in zip(sub, knock, tail)]
    write_wav(path, _fade_edges(_normalize(_soft_clip(mixed, 1.8), 0.82), sr, release=0.06), sr)


def make_whoosh(path: Path) -> None:
    """Air whoosh: noise through a rising-then-falling bandpass with a smooth swell."""
    sr = 44100
    length = int(sr * 0.7)
    rng = random.Random(29)
    noise = [rng.random() * 2 - 1 for _ in range(length)]

    def band_top(i: int) -> float:
        p = i / length
        # Sweep the band up through the swell, then relax down at the release.
        return 350 + 2400 * math.sin(min(1.0, p / 0.72) * math.pi * 0.5) * (1.0 - 0.4 * max(0.0, (p - 0.72) / 0.28))

    swept = _bandpass(noise, sr, 240, band_top)
    swept = _one_pole_highpass(swept, sr, 180)

    shaped: List[float] = []
    for i, x in enumerate(swept):
        p = i / length
        env = math.sin(math.pi * min(1.0, p)) ** 1.7
        body = math.sin(2 * math.pi * (140 + 320 * p) * (i / sr)) * 0.07 * env
        shaped.append(x * env * 1.15 + body)
    write_wav(path, _fade_edges(_normalize(_soft_clip(shaped, 1.3), 0.55), sr, attack=0.015, release=0.05), sr)


class AvatarTaxApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1180x760")
        self.root.minsize(1040, 660)
        self.app_root = Path(__file__).resolve().parent
        if load_dotenv:
            load_dotenv(self.app_root / ".env")
        self.settings = load_settings(self.app_root)
        self.avatars_dir = self.app_root / "avatars"
        self.avatars_dir.mkdir(parents=True, exist_ok=True)
        (self.app_root / "work").mkdir(exist_ok=True)
        (self.app_root / "zips").mkdir(exist_ok=True)
        (self.app_root / "renderer" / "public").mkdir(parents=True, exist_ok=True)

        self.avatar_paths: List[Path] = []
        self.review_jobs: List[BuildJob] = []
        self._building = False
        self._review_window_open = False

        self.project_title = tk.StringVar(value=str(self.settings.get("project_title") or ""))
        saved_provider = str(self.settings.get("planning_provider") or "derouter_gpt")
        self.planning_provider = tk.StringVar(value=PLANNING_PROVIDER_LABELS.get(saved_provider, "Derouter GPT"))
        self.model_name = tk.StringVar(value=str(self.settings.get("model_name") or default_model(saved_provider)))
        saved_transcription = str(self.settings.get("transcription_provider") or "local_mac")
        self.transcription_provider = tk.StringVar(
            value=TRANSCRIPTION_PROVIDER_LABELS.get(saved_transcription, "Local fast (word-level sync)")
        )
        self.image_policy = tk.StringVar(value="Auto: about 1-2 useful inserts/min")
        self.avatars_label = tk.StringVar(value=str(self.avatars_dir))
        self.job_count_label = tk.StringVar(value="No avatars scanned yet.")
        self._server_proc: Optional[subprocess.Popen[str]] = None

        self._build_ui()
        self.planning_provider.trace_add("write", self.on_provider_change)
        for var in (self.project_title, self.model_name, self.transcription_provider):
            var.trace_add("write", lambda *_: self.save_settings())
        self.root.after(200, self.scan_avatars)

    def _build_ui(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Heading.TLabel", font=("Helvetica", 18, "bold"))
        style.configure("Primary.TButton", font=("Helvetica", 12, "bold"), padding=(14, 9))
        style.configure("TButton", padding=(10, 7))

        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill=tk.BOTH, expand=True)
        header = ttk.Frame(outer)
        header.pack(fill=tk.X)
        ttk.Label(header, text="Avatar Tax", style="Heading.TLabel").pack(side=tk.LEFT)
        self.scan_btn = ttk.Button(header, text="Scan", command=self.scan_avatars)
        self.scan_btn.pack(side=tk.RIGHT)
        self.review_btn = ttk.Button(header, text="Review (0)", command=self.open_review_window, state=tk.DISABLED)
        self.review_btn.pack(side=tk.RIGHT, padx=(0, 8))

        main = ttk.PanedWindow(outer, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True, pady=(14, 0))
        left = ttk.Frame(main, padding=10)
        right = ttk.Frame(main, padding=10)
        main.add(left, weight=1)
        main.add(right, weight=2)

        project = ttk.LabelFrame(left, text="Project")
        project.pack(fill=tk.X, pady=(0, 12))
        form = ttk.Frame(project, padding=8)
        form.pack(fill=tk.X)
        ttk.Label(form, text="Avatars folder").grid(row=0, column=0, sticky="w", pady=4)
        folder_row = ttk.Frame(form)
        folder_row.grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Entry(folder_row, textvariable=self.avatars_label, state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(folder_row, text="Open", command=self.open_avatars_folder).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(form, text="Title override").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(form, textvariable=self.project_title).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="Planning").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Combobox(
            form,
            textvariable=self.planning_provider,
            values=list(PLANNING_PROVIDER_LABELS.values()),
            state="readonly",
        ).grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="Model").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(form, textvariable=self.model_name).grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="Transcription").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Combobox(
            form,
            textvariable=self.transcription_provider,
            values=list(TRANSCRIPTION_PROVIDER_LABELS.values()),
            state="readonly",
        ).grid(row=4, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="Image inserts").grid(row=5, column=0, sticky="w", pady=4)
        ttk.Label(form, textvariable=self.image_policy, foreground="#555").grid(row=5, column=1, sticky="w", pady=4)
        form.columnconfigure(1, weight=1)

        jobs = ttk.LabelFrame(left, text="Detected avatars")
        jobs.pack(fill=tk.BOTH, expand=True, pady=(0, 12))
        jobs_inner = ttk.Frame(jobs, padding=8)
        jobs_inner.pack(fill=tk.BOTH, expand=True)
        ttk.Label(jobs_inner, textvariable=self.job_count_label, foreground="#555").pack(anchor="w", pady=(0, 6))
        list_frame = ttk.Frame(jobs_inner)
        list_frame.pack(fill=tk.BOTH, expand=True)
        self.jobs_list = tk.Listbox(list_frame, height=8, exportselection=False, font=("Helvetica", 12))
        jobs_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.jobs_list.yview)
        self.jobs_list.configure(yscrollcommand=jobs_scroll.set)
        self.jobs_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        jobs_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        actions = ttk.LabelFrame(left, text="Actions")
        actions.pack(fill=tk.X)
        actions_inner = ttk.Frame(actions, padding=8)
        actions_inner.pack(fill=tk.X)
        self.build_btn = ttk.Button(
            actions_inner,
            text="Build All Avatars",
            style="Primary.TButton",
            command=self.start_build,
        )
        self.build_btn.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(actions_inner, text="Open Remotion Studio", command=self.open_studio).pack(fill=tk.X, pady=(0, 8))
        ttk.Button(actions_inner, text="Open Zips Folder", command=self.open_zips).pack(fill=tk.X)
        ttk.Button(left, text="Clean Files", command=self.clean_temp_files).pack(side=tk.BOTTOM, fill=tk.X, pady=(12, 0))

        ttk.Label(right, text="Progress", style="Heading.TLabel").pack(anchor="w")
        self.log_text = scrolledtext.ScrolledText(
            right,
            height=28,
            wrap=tk.WORD,
            bg="#111318",
            fg="#f5f7fb",
            insertbackground="#ffffff",
            font=("Menlo", 11),
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.log("Put avatar videos in avatars/, then press Build All Avatars. Launch scans the folder automatically.")

    def save_settings(self) -> None:
        self.settings.update(
            {
                "project_title": self.project_title.get(),
                "planning_provider": provider_key(self.planning_provider.get()),
                "model_name": self.model_name.get(),
                "transcription_provider": transcription_key(self.transcription_provider.get()),
            }
        )
        save_settings(self.app_root, self.settings)

    def on_provider_change(self, *_: Any) -> None:
        provider = provider_key(self.planning_provider.get())
        self.model_name.set(default_model(provider))
        self.save_settings()

    def scan_avatars(self) -> None:
        self.avatars_dir.mkdir(parents=True, exist_ok=True)
        self.avatar_paths = sorted(
            [path for path in self.avatars_dir.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS],
            key=lambda path: path.name.lower(),
        )
        self.jobs_list.delete(0, tk.END)
        for path in self.avatar_paths:
            self.jobs_list.insert(tk.END, path.name)
        count = len(self.avatar_paths)
        self.job_count_label.set(f"{count} avatar video{'s' if count != 1 else ''} found in avatars/.")
        if count:
            self.log(f"Detected {count} avatar video(s).")
        else:
            self.log("No avatar videos found yet. Add mp4/mov/mkv/webm files to avatars/.")

    def open_avatars_folder(self) -> None:
        self.avatars_dir.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["open", str(self.avatars_dir)])

    def log(self, message: str) -> None:
        def append() -> None:
            ts = time.strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{ts}] {message}\n")
            self.log_text.see(tk.END)

        self.root.after(0, append)

    def start_build(self) -> None:
        if self._building:
            return
        self.scan_avatars()
        if not self.avatar_paths:
            messagebox.showerror(APP_TITLE, "Put avatar videos in the avatars folder first.")
            return
        self.save_settings()
        self.review_jobs = []
        self.set_review_button(0, enabled=False)
        self._building = True
        self.build_btn.configure(state=tk.DISABLED)
        self.scan_btn.configure(state=tk.DISABLED)
        threading.Thread(target=self.build_worker, args=(list(self.avatar_paths),), daemon=True).start()

    def build_worker(self, videos: List[Path]) -> None:
        errors: List[str] = []
        try:
            title_override = self.project_title.get().strip() if len(videos) == 1 else ""
            if len(videos) > 1 and self.project_title.get().strip():
                self.log("Multiple avatars found; title override is ignored so each video gets its own title.")
            for index, video in enumerate(videos, start=1):
                try:
                    self.log(f"Preparing {index}/{len(videos)}: {video.name}")
                    job = self.prepare_build_job(video, title_override)
                    self.review_jobs.append(job)
                    self.root.after(0, lambda count=len(self.review_jobs): self.set_review_button(count, enabled=False))
                    self.log(f"{video.name}: ready for review.")
                except Exception as exc:
                    errors.append(f"{video.name}: {exc}")
                    self.log(f"{video.name}: failed: {exc}")
            if self.review_jobs:
                self.root.after(0, lambda: self.set_review_button(len(self.review_jobs), enabled=True))
                self.log(f"Review ready for {len(self.review_jobs)} video(s).")
            if errors:
                self.root.after(0, lambda: messagebox.showwarning(APP_TITLE, "Some videos failed:\n" + "\n".join(errors[:8])))
            elif not self.review_jobs:
                self.root.after(0, lambda: messagebox.showerror(APP_TITLE, "No videos were prepared."))
        finally:
            self._building = False
            self.root.after(0, lambda: self.build_btn.configure(state=tk.NORMAL))
            self.root.after(0, lambda: self.scan_btn.configure(state=tk.NORMAL))

    def prepare_build_job(self, video: Path, title_override: str = "") -> BuildJob:
        raw_title = title_override.strip()
        if looks_like_filename_title(raw_title, video.stem):
            raw_title = ""
        stem = safe_stem(video.stem)
        work_dir = self.app_root / "work" / stem
        public_dir = work_dir / "public"
        assets_dir = public_dir / "images"
        avatar_dir = public_dir / "avatar"
        shutil.rmtree(public_dir, ignore_errors=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        assets_dir.mkdir(parents=True, exist_ok=True)
        avatar_dir.mkdir(parents=True, exist_ok=True)

        self.log(f"{video.name}: reading duration...")
        duration = ffprobe_duration(video)
        self.log(f"{video.name}: duration {duration / 60:.1f} min")

        avatar_public = avatar_dir / f"{stem}.mp4"
        self.log(f"{video.name}: preparing stable avatar video...")
        try:
            prepare_stable_avatar_video(video, avatar_public)
        except Exception as exc:
            self.log(f"{video.name}: stable prep failed, using original file: {exc}")
            avatar_public = avatar_dir / f"{stem}{video.suffix.lower()}"
            shutil.copy2(video, avatar_public)

        transcript = ""
        transcript_chunks: List[TranscriptChunk] = []
        transcript_words: List[TranscriptWord] = []
        provider = transcription_key(self.transcription_provider.get())
        audio_path = work_dir / "voice.wav"
        if provider != "none":
            self.log(f"{video.name}: extracting audio...")
            extract_audio(video, audio_path)
            try:
                transcript_result = self.transcribe_with_recovery(audio_path, provider)
                transcript = transcript_result.text
                transcript_chunks = transcript_result.chunks
                transcript_words = transcript_result.words
                (work_dir / "transcript.txt").write_text(transcript, encoding="utf-8")
                sync_note = f", {len(transcript_words)} timed words" if transcript_words else ""
                self.log(f"{video.name}: transcript ready ({len(transcript.split())} words{sync_note}).")
            except Exception as exc:
                self.log(f"{video.name}: transcription failed, continuing with local timing: {exc}")
        else:
            self.log(f"{video.name}: transcription skipped.")

        title = raw_title or display_title_from_transcript(raw_title, transcript, video.stem)
        plan_provider = provider_key(self.planning_provider.get())
        model = self.model_name.get().strip() or default_model(plan_provider)
        image_target = target_image_count(duration, transcript)
        self.log(f"{video.name}: image insert goal up to {image_target}.")

        keep_existing_overlays = True
        if plan_provider == "local":
            self.log(f"{video.name}: using local planner.")
            plan = local_plan(title, transcript, duration, image_target=image_target)
            keep_existing_overlays = False
        else:
            try:
                plan = self.plan_with_recovery(
                    plan_provider,
                    model,
                    title,
                    transcript,
                    duration,
                    image_target,
                    transcript_chunks,
                    title_is_user_supplied=bool(raw_title),
                )
            except Exception as exc:
                self.log(f"{video.name}: AI director failed. Using local fallback. Reason: {exc}")
                plan = local_plan(title, transcript, duration, image_target=image_target)
                keep_existing_overlays = False

        plan = enhance_director_plan(
            plan,
            title,
            transcript,
            duration,
            image_target,
            keep_existing_overlays=keep_existing_overlays,
            transcript_chunks=transcript_chunks,
            transcript_words=transcript_words,
            log=self.log,
        )
        plan.title = display_title_from_transcript(plan.title, transcript, video.stem)
        if plan.images:
            self.log(f"{video.name}: fetching {len(plan.images)} optional image insert(s)...")
            self.fetch_plan_images(plan, assets_dir)
        else:
            self.log(f"{video.name}: no image inserts requested.")

        return BuildJob(
            video=video,
            stem=stem,
            title=plan.title,
            duration=duration,
            work_dir=work_dir,
            public_dir=public_dir,
            avatar_public=avatar_public,
            plan=plan,
        )

    def transcribe_with_recovery(self, audio: Path, provider: str) -> TranscriptResult:
        while True:
            try:
                if provider == "local_whisperx":
                    try:
                        return transcribe_whisperx(audio, self.log)
                    except Exception as exc:
                        self.log(
                            "WhisperX unavailable "
                            f"({brief_error(exc, 180)}; python={sys.executable}); "
                            "falling back to faster-whisper."
                        )
                        return transcribe_local(audio, self.log)
                if provider == "local_mac":
                    return transcribe_local(audio, self.log)
                return transcribe_openai(audio, self.log)
            except Exception as exc:
                if provider == "openai_mini" and recoverable_api_error(exc) and self.prompt_api_recovery("openai_mini", exc):
                    continue
                raise

    def plan_with_recovery(
        self,
        provider: str,
        model: str,
        title: str,
        transcript: str,
        duration: float,
        image_target: int,
        transcript_chunks: List[TranscriptChunk],
        title_is_user_supplied: bool,
    ) -> DirectorPlan:
        while True:
            try:
                return ai_director_plan_batched(
                    provider,
                    model,
                    title,
                    transcript,
                    duration,
                    image_target,
                    self.log,
                    transcript_chunks=transcript_chunks,
                    title_is_user_supplied=title_is_user_supplied,
                )
            except Exception as exc:
                if provider != "local" and recoverable_api_error(exc) and self.prompt_api_recovery(provider, exc):
                    continue
                raise

    def fetch_plan_images(self, plan: DirectorPlan, assets_dir: Path) -> None:
        used_urls: set[str] = set()
        fallback_pool = fallback_image_phrases(plan.title)
        for image in plan.images:
            try:
                choices: List[Dict[str, Any]] = []
                for attempt_query in image_query_attempts(image.query, image.caption, fallback_pool, image.index):
                    items = self.search_serper_with_recovery(attempt_query, limit=14)
                    choices = download_good_image_choices(items, assets_dir, image.index, used_urls=used_urls)
                    if choices:
                        if attempt_query != image.query:
                            self.log(f"Image {image.index}: retried with simpler query: {attempt_query}")
                            image.query = attempt_query
                        break
                if not choices:
                    image.use = False
                    self.log(f"Image {image.index}: no usable image for {image.query}")
                    continue
                image.choices = [
                    {
                        "path": f"images/{Path(choice['path']).name}",
                        "source": str(choice.get("source") or ""),
                        "width": choice.get("width"),
                        "height": choice.get("height"),
                        "quality_score": choice.get("quality_score"),
                        "quality_notes": choice.get("quality_notes") or [],
                    }
                    for choice in choices
                ]
                image.selected = 0
                found = image.choices[0]
                path = Path(found["path"])
                image.path = f"images/{path.name}"
                image.source = str(found.get("source") or "")
                self.log(f"Image {image.index}: {len(image.choices)} choice(s).")
            except Exception as exc:
                image.use = False
                self.log(f"Image {image.index}: failed: {exc}")

    def search_serper_with_recovery(self, query: str, limit: int) -> List[Dict[str, Any]]:
        while True:
            try:
                return search_serper_images(query, limit=limit)
            except Exception as exc:
                if recoverable_api_error(exc) and self.prompt_api_recovery("serper", exc):
                    continue
                raise

    def set_review_button(self, count: int, enabled: bool) -> None:
        self.review_btn.configure(text=f"Review ({count})", state=tk.NORMAL if enabled and count else tk.DISABLED)

    def open_review_window(self) -> None:
        if self._review_window_open:
            return
        jobs = list(self.review_jobs)
        if not jobs:
            messagebox.showinfo(APP_TITLE, "No prepared videos to review yet.")
            return
        self._review_window_open = True
        self.show_review_window(jobs)

    def show_review_window(self, jobs: List[BuildJob]) -> None:
        win = tk.Toplevel(self.root)
        win.title(f"Review Image Inserts - {len(jobs)} video{'s' if len(jobs) != 1 else ''}")
        win.geometry("1420x820")
        win.minsize(1120, 680)
        win.transient(self.root)

        header = ttk.Frame(win, padding=(14, 12, 14, 8))
        header.pack(fill=tk.X)
        ttk.Label(header, text="Review image inserts", font=("Helvetica", 18, "bold")).pack(side=tk.LEFT)
        ttk.Label(
            header,
            text="Down/Up = image insert, Right/Left = image choice. Confirm once to create all zip packages.",
            foreground="#555",
        ).pack(side=tk.LEFT, padx=(18, 0))

        notebook = ttk.Notebook(win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 10))
        tab_states: List[Dict[str, Any]] = []

        for job in jobs:
            tab = ttk.Frame(notebook, padding=12)
            notebook.add(tab, text=job.stem[:22])
            tab_states.append(self.build_review_tab(win, tab, job))

        footer = ttk.Frame(win, padding=(14, 0, 14, 12))
        footer.pack(fill=tk.X)
        ttk.Button(footer, text="Cancel", command=lambda: close_without_build()).pack(side=tk.LEFT)
        ttk.Button(footer, text="Confirm and Build All", style="Primary.TButton", command=lambda: confirm()).pack(side=tk.RIGHT)

        def active_state() -> Optional[Dict[str, Any]]:
            try:
                return tab_states[notebook.index(notebook.select())]
            except Exception:
                return tab_states[0] if tab_states else None

        def key_move_item(delta: int) -> str:
            state = active_state()
            if state and state.get("move_item"):
                state["move_item"](delta)
            return "break"

        def key_move_choice(delta: int) -> str:
            state = active_state()
            if state and state.get("move_choice"):
                state["move_choice"](delta)
            return "break"

        def close_without_build() -> None:
            self._review_window_open = False
            win.destroy()

        def confirm() -> None:
            for state in tab_states:
                apply_all = state.get("apply_all")
                if apply_all:
                    apply_all()
            self._review_window_open = False
            win.destroy()
            self.start_finalize_jobs(jobs)

        win.bind("<Down>", lambda _event: key_move_item(1))
        win.bind("<Up>", lambda _event: key_move_item(-1))
        win.bind("<Right>", lambda _event: key_move_choice(1))
        win.bind("<Left>", lambda _event: key_move_choice(-1))
        win.protocol("WM_DELETE_WINDOW", close_without_build)
        win.focus_set()

    def build_review_tab(self, win: tk.Toplevel, tab: ttk.Frame, job: BuildJob) -> Dict[str, Any]:
        usable = [item for item in job.plan.images if item.path and item.use]
        for item in usable:
            if not item.choices and item.path:
                item.choices = [{"path": item.path, "source": item.source}]
                item.selected = 0
        tab.columnconfigure(0, weight=0)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(1, weight=1)
        ttk.Label(tab, text=f"{job.video.name} · {len(usable)} image insert(s)", foreground="#555").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        state: Dict[str, Any] = {"index": 0, "refreshing": False, "usable": usable}
        if not usable:
            ttk.Label(tab, text="No usable image inserts for this video. It will still build normally.").grid(
                row=1, column=0, sticky="nw"
            )
            return {"apply_all": lambda: None}

        left = ttk.Frame(tab)
        left.grid(row=1, column=0, sticky="nsw", padx=(0, 14))
        listbox = tk.Listbox(left, width=50, activestyle="dotbox", exportselection=False, font=("Helvetica", 12))
        listbox_scroll = ttk.Scrollbar(left, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=listbox_scroll.set)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        listbox_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        right = ttk.Frame(tab)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        preview = tk.Label(right, bg="#1a1a1a", fg="#ffffff", text="Preview", width=760, height=24)
        preview.grid(row=0, column=0, sticky="nsew")
        title_label = ttk.Label(right, text="", font=("Helvetica", 17, "bold"), wraplength=760)
        title_label.grid(row=1, column=0, sticky="ew", pady=(12, 4))
        detail_label = ttk.Label(right, text="", justify=tk.LEFT, wraplength=800, foreground="#444")
        detail_label.grid(row=2, column=0, sticky="ew", pady=(0, 8))

        controls = ttk.Frame(right)
        controls.grid(row=3, column=0, sticky="ew")
        use_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text="Use image", variable=use_var, command=lambda: set_use()).pack(side=tk.LEFT)
        ttk.Button(controls, text="Previous image", command=lambda: move_choice(-1)).pack(side=tk.LEFT, padx=(16, 6))
        ttk.Button(controls, text="Next image", command=lambda: move_choice(1)).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Button(controls, text="Previous insert", command=lambda: move_item(-1)).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(controls, text="Next insert", command=lambda: move_item(1)).pack(side=tk.LEFT)

        def choice_text(item: PlannedImage) -> str:
            total = max(1, len(item.choices))
            return f"{item.selected + 1}/{total}"

        def apply_selected_choice(item: PlannedImage) -> None:
            if not item.choices:
                return
            item.selected = max(0, min(item.selected, len(item.choices) - 1))
            choice = item.choices[item.selected]
            item.path = str(choice.get("path") or item.path)
            item.source = str(choice.get("source") or item.source)

        def row_text(pos: int, item: PlannedImage) -> str:
            status = "use" if item.use else "skip"
            return f"{pos + 1:02d}  {status:<4}  {choice_text(item):<5}  {item.caption[:42]}"

        def refresh_list() -> None:
            state["refreshing"] = True
            listbox.delete(0, tk.END)
            for pos, item in enumerate(usable):
                listbox.insert(tk.END, row_text(pos, item))
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(state["index"])
            listbox.activate(state["index"])
            listbox.see(state["index"])
            state["refreshing"] = False

        def show_item(pos: int) -> None:
            state["index"] = max(0, min(len(usable) - 1, pos))
            item = usable[state["index"]]
            apply_selected_choice(item)
            use_var.set(bool(item.use))
            refresh_list()
            local = job.public_dir / item.path
            try:
                with Image.open(local) as img:
                    img = img.convert("RGB")
                    img.thumbnail((840, 470))
                    photo = ImageTk.PhotoImage(img, master=win)
                preview.configure(image=photo, text="")
                preview.image = photo
                win._preview_ref = photo  # type: ignore[attr-defined]
            except Exception:
                preview.configure(image="", text="Preview failed")
                preview.image = None
            title_label.configure(text=f"Insert {state['index'] + 1}: {item.caption}")
            detail_label.configure(
                text=(
                    f"Time: {item.time:.1f}s  Duration: {item.duration:.1f}s  Choice: {choice_text(item)}\n"
                    f"Query: {item.query}\nSource: {item.source or 'unknown'}"
                )
            )

        def set_use() -> None:
            item = usable[state["index"]]
            item.use = bool(use_var.get())
            refresh_list()

        def move_item(delta: int) -> str:
            show_item(state["index"] + delta)
            return "break"

        def move_choice(delta: int) -> str:
            item = usable[state["index"]]
            if item.choices:
                item.selected = (item.selected + delta) % len(item.choices)
                apply_selected_choice(item)
            show_item(state["index"])
            return "break"

        def on_select(_event: tk.Event) -> None:
            if state["refreshing"]:
                return
            selection = listbox.curselection()
            if selection:
                show_item(int(selection[0]))

        def apply_all() -> None:
            for item in usable:
                apply_selected_choice(item)

        listbox.bind("<<ListboxSelect>>", on_select)
        show_item(0)
        state.update({"move_item": move_item, "move_choice": move_choice, "apply_all": apply_all})
        return state

    def start_finalize_jobs(self, jobs: List[BuildJob]) -> None:
        self.build_btn.configure(state=tk.DISABLED)
        self.review_btn.configure(state=tk.DISABLED)
        threading.Thread(target=self.finalize_jobs_worker, args=(jobs,), daemon=True).start()

    def finalize_jobs_worker(self, jobs: List[BuildJob]) -> None:
        zips_dir = self.app_root / "zips"
        zips_dir.mkdir(exist_ok=True)
        completed: List[Path] = []
        try:
            for job in jobs:
                self.log(f"{job.video.name}: writing Remotion plan and zip...")
                self.prune_unused_images(job.plan, job.public_dir)
                sfx_map = generate_sfx_files(job.public_dir / "sfx")
                data = self.plan_to_json(job.plan, job.avatar_public, job.public_dir, sfx_map)
                (job.public_dir / "avatar_plan.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
                (job.work_dir / "avatar_plan.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
                zip_path = zips_dir / f"{job.stem}.zip"
                self.write_zip(zip_path, job.public_dir)
                job.zip_path = zip_path
                job.status = "zipped"
                completed.append(zip_path)
                self.log(f"{job.video.name}: zip ready: {zip_path.name}")
            if jobs:
                self.copy_public_for_preview(jobs[-1].public_dir)
            self.root.after(
                0,
                lambda: messagebox.showinfo(
                    APP_TITLE,
                    "Build complete:\n" + "\n".join(path.name for path in completed),
                ),
            )
        except Exception as exc:
            self.log(f"Finalize failed: {exc}")
            self.root.after(0, lambda: messagebox.showerror(APP_TITLE, str(exc)))
        finally:
            self.root.after(0, lambda: self.build_btn.configure(state=tk.NORMAL))
            self.root.after(0, lambda: self.set_review_button(len(self.review_jobs), enabled=bool(self.review_jobs)))

    def copy_public_for_preview(self, source_public: Path) -> None:
        target = self.app_root / "renderer" / "public"
        if source_public.resolve() == target.resolve():
            return
        target.mkdir(parents=True, exist_ok=True)
        for child in target.iterdir():
            if child.name == ".gitkeep":
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        for child in source_public.iterdir():
            dest = target / child.name
            if child.is_dir():
                shutil.copytree(child, dest)
            elif child.is_file():
                shutil.copy2(child, dest)

    def prompt_api_recovery(self, service: str, exc: Exception) -> bool:
        env_name = service_env_var(service)
        label = service_label(service)
        result = {"retry": False}
        done = threading.Event()

        def show() -> None:
            win = tk.Toplevel(self.root)
            win.title(f"{label} needs attention")
            win.geometry("560x360")
            win.transient(self.root)
            win.grab_set()
            key_var = tk.StringVar()

            frame = ttk.Frame(win, padding=18)
            frame.pack(fill=tk.BOTH, expand=True)
            ttk.Label(frame, text=f"{label} could not continue.", font=("Helvetica", 16, "bold")).pack(anchor="w")
            ttk.Label(
                frame,
                text=(
                    f"If credit is empty, top up {label}, then click Continue.\n"
                    f"If the key changed, paste the new {env_name} below."
                ),
                wraplength=500,
                foreground="#444",
            ).pack(anchor="w", pady=(10, 8))
            error_box = tk.Text(frame, height=5, wrap=tk.WORD, bg="#f6f6f6")
            error_box.insert("1.0", brief_error(exc))
            error_box.configure(state=tk.DISABLED)
            error_box.pack(fill=tk.X, pady=(0, 12))
            ttk.Label(frame, text=f"New {env_name} (optional)").pack(anchor="w")
            ttk.Entry(frame, textvariable=key_var, show="*", width=58).pack(fill=tk.X, pady=(4, 14))
            buttons = ttk.Frame(frame)
            buttons.pack(fill=tk.X)

            def close(retry: bool) -> None:
                new_key = key_var.get().strip()
                if retry and new_key:
                    os.environ[env_name] = new_key
                    try:
                        set_env_file_value(self.app_root / ".env", env_name, new_key)
                        self.log(f"Saved new {env_name} to .env.")
                    except Exception as save_exc:
                        self.log(f"Could not save {env_name} to .env: {save_exc}")
                result["retry"] = retry
                win.grab_release()
                win.destroy()
                done.set()

            ttk.Button(buttons, text="Use fallback / Skip", command=lambda: close(False)).pack(side=tk.LEFT)
            ttk.Button(buttons, text="Continue", style="Primary.TButton", command=lambda: close(True)).pack(side=tk.RIGHT)
            win.protocol("WM_DELETE_WINDOW", lambda: close(False))
            win.focus_set()

        self.root.after(0, show)
        done.wait()
        return bool(result["retry"])

    def prune_unused_images(self, plan: DirectorPlan, public_dir: Path) -> None:
        keep = {image.path for image in plan.images if image.use and image.path}
        images_dir = public_dir / "images"
        if not images_dir.exists():
            return
        for path in images_dir.iterdir():
            if not path.is_file() or path.name == ".gitkeep":
                continue
            rel = f"images/{path.name}"
            if rel not in keep:
                path.unlink(missing_ok=True)

    def plan_to_json(self, plan: DirectorPlan, avatar_path: Path, public_dir: Path, sfx_map: Dict[str, str]) -> Dict[str, Any]:
        return {
            "title": plan.title,
            "duration": plan.duration,
            "fps": 30,
            "avatarVideo": str(avatar_path.relative_to(public_dir)).replace(os.sep, "/"),
            "sfx": sfx_map,
            "chapters": plan.chapters,
            "zooms": plan.zooms,
            "overlays": sorted(plan.overlays, key=lambda item: float(item.get("time") or 0)),
            "images": [
                {
                    "time": image.time,
                    "duration": image.duration,
                    "path": image.path,
                    "caption": image.caption,
                    "source": image.source,
                }
                for image in plan.images
                if image.use and image.path
            ],
        }

    def write_zip(self, zip_path: Path, public_dir: Path) -> None:
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in public_dir.rglob("*"):
                if path.is_file() and path.name != ".DS_Store":
                    zf.write(path, path.relative_to(public_dir))

    def renderer_dir(self) -> Path:
        return self.app_root / "renderer"

    def open_studio(self) -> None:
        renderer = self.renderer_dir()
        if not (renderer / "node_modules").exists():
            messagebox.showinfo(APP_TITLE, "Run npm install inside renderer first.")
            return
        if self._server_proc and self._server_proc.poll() is None:
            subprocess.Popen(["open", "http://localhost:3000"])
            return
        self._server_proc = subprocess.Popen(["npm", "run", "dev"], cwd=renderer)
        time.sleep(1)
        subprocess.Popen(["open", "http://localhost:3000"])

    def open_zips(self) -> None:
        path = self.app_root / "zips"
        path.mkdir(exist_ok=True)
        subprocess.Popen(["open", str(path)])

    def clean_temp_files(self) -> None:
        if not messagebox.askyesno(APP_TITLE, "Delete work files, public assets, and zips from previous builds?"):
            return
        for name in ("work", "zips"):
            shutil.rmtree(self.app_root / name, ignore_errors=True)
            (self.app_root / name).mkdir(exist_ok=True)
        public = self.app_root / "renderer" / "public"
        for child in public.iterdir() if public.exists() else []:
            if child.name == ".gitkeep":
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        self.review_jobs = []
        self.set_review_button(0, enabled=False)
        self.scan_avatars()
        self.log("Temp files cleaned.")


def main() -> None:
    root = tk.Tk()
    app = AvatarTaxApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
