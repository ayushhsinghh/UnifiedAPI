"""
SRT subtitle utilities for Riva ASR transcription.

Provides helpers to convert NVIDIA Riva offline recognition responses
into standard SRT subtitle files, with support for chunked audio
(time offset merging).

It also post-processes the 30-second chunks returned by Riva into
smaller ~10-second segments or chunks of max 100 characters, evenly
distributing the text across the 30-second time gap.
"""


def seconds_to_srt_timestamp(total_seconds: float) -> str:
    """Convert seconds to SRT timestamp format: HH:MM:SS,mmm"""
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    milliseconds = int(round((total_seconds - int(total_seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def split_text_into_segments(text: str, duration: float, max_chars: int = 100, max_duration: float = 10.0):
    """
    Splits a transcription string and its duration into smaller chunks.
    Ensures no chunk exceeds max_chars or max_duration. Time is distributed
    proportionally based on character count.
    
    Args:
        text: The full transcript string for the interval
        duration: The time duration in seconds for the interval
        max_chars: Maximum characters allowed per segment
        max_duration: Maximum time duration allowed per segment
        
    Returns:
        List of tuples: (relative_start, relative_end, segment_text)
    """
    words = text.split()
    if not words:
        return []

    # Calculate optimal number of segments based on both constraints
    total_chars = len(text)
    
    # If the text is short enough (<= 80 chars), keep it as a single 30s segment
    if total_chars <= 80:
        return [(0.0, duration, text)]
    
    # Needs at least this many segments for length constraint
    min_segs_for_length = max(1, (total_chars + max_chars - 1) // max_chars)
    
    # Needs at least this many segments for time constraint
    min_segs_for_time = max(1, int(duration // max_duration) + (1 if duration % max_duration > 0 else 0))
    
    num_segments = max(min_segs_for_length, min_segs_for_time)

    # If 1 segment is enough, return it
    if num_segments == 1:
        return [(0.0, duration, text)]

    # Distribute words evenly across segments
    segments = []
    words_per_seg = max(1, len(words) // num_segments)
    
    current_word_idx = 0
    current_time = 0.0
    
    for i in range(num_segments):
        if i == num_segments - 1:
            seg_words = words[current_word_idx:]
        else:
            seg_words = words[current_word_idx : current_word_idx + words_per_seg]
            
        current_word_idx += len(seg_words)
        
        seg_text = " ".join(seg_words)
        
        # Calculate time proportionally by character length
        seg_duration = duration * (len(seg_text) / max(1, total_chars))
        
        # If this is the last segment, ensure it reaches the exact end duration
        if i == num_segments - 1:
            seg_end = duration
        else:
            seg_end = current_time + seg_duration
            
        segments.append((current_time, seg_end, seg_text))
        current_time = seg_end
        
    return segments


def extract_srt_entries(response, time_offset_seconds: float = 0.0) -> list:
    """
    Extract SRT entries from a Riva offline recognition response.

    Each result in the response represents ~30s of audio with an
    ``audio_processed`` field (cumulative seconds within that chunk).
    The text is then post-processed to split it into smaller segments
    (max 10s or 100 chars).
    ``time_offset_seconds`` shifts all timestamps to account for the
    chunk's position in the full audio.

    Args:
        response: Riva RecognizeResponse object.
        time_offset_seconds: Seconds offset for this chunk.

    Returns:
        List of (start_seconds, end_seconds, transcript) tuples.
    """
    entries = []
    chunk_duration = 30.0

    for result in response.results:
        if len(result.alternatives) == 0:
            continue

        transcript = result.alternatives[0].transcript.strip()
        if not transcript:
            continue

        # audio_processed is cumulative within the chunk (30.0, 60.0, 90.0, ...)
        end_seconds = result.audio_processed + time_offset_seconds
        start_seconds = max(time_offset_seconds, end_seconds - chunk_duration)
        
        actual_chunk_duration = end_seconds - start_seconds

        # Post-process: Split the ~30s chunk into smaller segments
        sub_segments = split_text_into_segments(
            text=transcript, 
            duration=actual_chunk_duration,
            max_chars=100,
            max_duration=10.0
        )
        
        for relative_start, relative_end, part_text in sub_segments:
            abs_start = start_seconds + relative_start
            abs_end = start_seconds + relative_end
            entries.append((abs_start, abs_end, part_text))

    return entries


def write_combined_srt(all_entries: list, output_path: str) -> None:
    """
    Write a combined SRT file from (start_seconds, end_seconds, transcript) tuples.

    Args:
        all_entries: List of (start_seconds, end_seconds, transcript) tuples.
        output_path: Path for the .srt file.
    """
    srt_blocks = []
    for idx, (start_s, end_s, text) in enumerate(all_entries, start=1):
        start_ts = seconds_to_srt_timestamp(start_s)
        end_ts = seconds_to_srt_timestamp(end_s)
        srt_blocks.append(f"{idx}\n{start_ts} --> {end_ts}\n{text}\n")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_blocks) + "\n")