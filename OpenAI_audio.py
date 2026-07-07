"""
Translate Japanese audio (job_20ch.wav) to English SRT subtitles
using the OpenAI Whisper-1 translation API.

The audio file exceeds the 25 MB API limit, so it is split into
smaller chunks. Each chunk is translated independently and the
resulting SRT segments are merged with corrected timestamps.

Usage:
    export OPENAI_API_KEY="sk-..."
    python OpenAI_audio.py
"""

import os
import re
import math
import tempfile
from pathlib import Path

from openai import OpenAI
from pydub import AudioSegment

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
AUDIO_PATH = Path("/home/ubuntu/video-transcriber/job_x8fd.wav")
OUTPUT_SRT = AUDIO_PATH.with_suffix(".srt")  # job_20ch.srt


# Maximum chunk duration in milliseconds (10 minutes).
# Whisper-1 accepts files up to 25 MB; 10-min mono WAV chunks stay well
# under that limit even at 44.1 kHz / 16-bit.
CHUNK_DURATION_MS = 10 * 60 * 1000  # 10 minutes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parse_srt_timestamp(ts: str) -> float:
    """Convert an SRT timestamp (HH:MM:SS,mmm) to seconds."""
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def format_srt_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def offset_srt(srt_text: str, offset_seconds: float, start_index: int) -> tuple[str, int]:
    """
    Shift all timestamps in *srt_text* by *offset_seconds* and
    re-number the cues starting from *start_index*.

    Returns (adjusted_srt_string, next_index).
    """
    timestamp_pattern = re.compile(
        r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})"
    )

    lines = srt_text.strip().splitlines()
    result_lines: list[str] = []
    idx = start_index

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Skip blank lines between cues
        if not line:
            i += 1
            continue

        # Expect a cue index (digit line) – replace with our running index
        if line.isdigit():
            result_lines.append(str(idx))
            i += 1
            if i >= len(lines):
                break

            # Next line should be the timestamp line
            ts_line = lines[i].strip()
            match = timestamp_pattern.match(ts_line)
            if match:
                start = parse_srt_timestamp(match.group(1)) + offset_seconds
                end = parse_srt_timestamp(match.group(2)) + offset_seconds
                result_lines.append(
                    f"{format_srt_timestamp(start)} --> {format_srt_timestamp(end)}"
                )
            else:
                result_lines.append(ts_line)
            i += 1

            # Collect subtitle text lines until blank line or next cue
            while i < len(lines) and lines[i].strip():
                result_lines.append(lines[i].strip())
                i += 1

            result_lines.append("")  # blank separator
            idx += 1
        else:
            i += 1

    return "\n".join(result_lines), idx


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    client = OpenAI()  # uses OPENAI_API_KEY env var

    print(f"Loading audio: {AUDIO_PATH}")
    audio = AudioSegment.from_wav(str(AUDIO_PATH))
    total_duration_ms = len(audio)
    num_chunks = math.ceil(total_duration_ms / CHUNK_DURATION_MS)

    print(f"Total duration : {total_duration_ms / 1000:.1f}s")
    print(f"Chunk size     : {CHUNK_DURATION_MS / 1000:.0f}s")
    print(f"Number of chunks: {num_chunks}")

    all_srt_parts: list[str] = []
    cue_index = 1

    with tempfile.TemporaryDirectory() as tmp_dir:
        for chunk_num in range(num_chunks):
            start_ms = chunk_num * CHUNK_DURATION_MS
            end_ms = min(start_ms + CHUNK_DURATION_MS, total_duration_ms)
            chunk = audio[start_ms:end_ms]

            # Export chunk as mono WAV to keep file size small
            chunk_path = os.path.join(tmp_dir, f"chunk_{chunk_num:03d}.wav")
            chunk.export(chunk_path, format="wav", parameters=["-ac", "1"])
            chunk_size_mb = os.path.getsize(chunk_path) / (1024 * 1024)

            print(
                f"\n--- Chunk {chunk_num + 1}/{num_chunks} ---"
                f"\n  Range : {start_ms / 1000:.1f}s – {end_ms / 1000:.1f}s"
                f"\n  Size  : {chunk_size_mb:.1f} MB"
            )

            with open(chunk_path, "rb") as audio_file:
                translation = client.audio.translations.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="srt",
                )

            if not translation or not translation.strip():
                print("  (no speech detected in this chunk)")
                continue

            # Shift timestamps by the chunk's start offset and renumber cues
            offset_seconds = start_ms / 1000
            adjusted_srt, cue_index = offset_srt(
                translation, offset_seconds, cue_index
            )
            all_srt_parts.append(adjusted_srt)

    # Write merged SRT
    final_srt = "\n".join(all_srt_parts).strip() + "\n"
    OUTPUT_SRT.write_text(final_srt, encoding="utf-8")
    print(f"\n✅ SRT file saved to: {OUTPUT_SRT}")


if __name__ == "__main__":
    main()