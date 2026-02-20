import subprocess
import logging
import json
from faster_whisper import WhisperModel
from storage import JobStatus
from database import get_job, update_job_status, update_job_progress, update_job_completion, update_job_error

logger = logging.getLogger(__name__)

# Model cache to avoid reloading the same model
_model_cache = {}

def get_model(model_name: str):
    """Get or create a WhisperModel instance"""
    if model_name not in _model_cache:
        logger.info(f"Loading WhisperModel '{model_name}'...")
        _model_cache[model_name] = WhisperModel(
            model_name,
            device="cpu",
            compute_type="int8",
            cpu_threads=4,
            num_workers=2
        )
        logger.info(f"WhisperModel '{model_name}' loaded successfully")
    return _model_cache[model_name]

def get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds using ffprobe"""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1:noprint_wrappers=1",
                audio_path
            ],
            capture_output=True,
            text=True,
            check=True
        )
        duration = float(result.stdout.strip())
        logger.info(f"Audio duration: {duration:.2f} seconds")
        return duration
    except Exception as e:
        logger.warning(f"Could not get audio duration: {str(e)}. Progress tracking will be limited.")
        return 0

def extract_audio(video_path: str, audio_path: str):
    logger.info(f"Extracting audio from {video_path} to {audio_path}")
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", video_path,
                "-ac", "1",
                "-ar", "16000",
                "-threads", "4",  # Use all CPU cores for ffmpeg
                audio_path
            ],
            check=True,
            capture_output=True
        )
        logger.info(f"Audio extraction completed successfully")
    except subprocess.CalledProcessError as e:
        logger.error(f"Audio extraction failed: {str(e)}", exc_info=True)
        raise

def transcribe_job(job_id: str):
    job = get_job(job_id)
    if not job:
        logger.error(f"Job {job_id} not found in database")
        return
    
    logger.info(f"Starting transcription for job {job_id}")
    update_job_status(job_id, JobStatus.RUNNING)

    try:
        extract_audio(job["video"], job["audio"])
        
        # Get audio duration for progress tracking
        audio_duration = get_audio_duration(job["audio"])
        
        # Get the model to use (defaults to 'base' if not specified)
        model_name = job.get("model", "base")
        logger.info(f"Beginning transcription with model={model_name}, language={job.get('language')}, translate={job.get('translate')}")
        
        model = get_model(model_name)

        segments, info = model.transcribe(
            job["audio"],
            language=job.get("language"),
            task="translate" if job.get("translate") else "transcribe",
            beam_size=5,  # Changed from default 5 - much faster, minimal accuracy loss
            vad_filter=True,  # Skip silence - significant speedup
            vad_parameters=dict(min_silence_duration_ms=500)  # Adjust based on your content
        )
        logger.info(f"Transcription completed. Detected language: {info.language}")

        # Stream segments instead of converting to list
        with open(job["srt"], "w", encoding="utf-8") as f:
            segment_count = 0
            for seg in segments:
                segment_count += 1
                f.write(f"{segment_count}\n")
                f.write(f"{format_ts(seg.start)} --> {format_ts(seg.end)}\n")
                f.write(seg.text.strip() + "\n\n")
                
                # Update progress based on time (using segment end time vs total audio duration)
                if audio_duration > 0:
                    # Calculate progress as percentage of audio processed
                    progress_percentage = min(int((seg.end / audio_duration) * 100), 99)  # Cap at 99% until completion
                    success = update_job_progress(job_id, segment_count, progress_percentage)
                    if success:
                        logger.debug(f"Job {job_id} progress: {segment_count} segments, {progress_percentage}% complete")
                    else:
                        logger.warning(f"Job {job_id} failed to update progress")
                else:
                    # Fallback: just update segment count if we don't have duration
                    success = update_job_progress(job_id, segment_count, segment_count)
                    if success:
                        logger.debug(f"Job {job_id} progress: {segment_count} segments transcribed")
                    else:
                        logger.warning(f"Job {job_id} failed to update progress at {segment_count} segments")
        
        logger.debug(f"SRT file written with {segment_count} segments")
        update_job_completion(job_id, info.language)
        update_job_status(job_id, JobStatus.DONE)
        logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        logger.error(f"Job {job_id} failed with error: {str(e)}", exc_info=True)
        update_job_error(job_id, str(e))
        update_job_status(job_id, JobStatus.FAILED)


def format_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:06.3f}".replace(".", ",")