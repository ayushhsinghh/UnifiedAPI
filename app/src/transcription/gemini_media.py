"""Bounded-memory media preparation, exact sample fitting, and subtitle assembly."""
import asyncio
import array
import json
import math
import os
import shutil
import sys
import wave
from fractions import Fraction
from pathlib import Path

IN_RATE = 16000
OUT_RATE = 24000


class MediaError(Exception):
    pass


async def command(*args):
    process = await asyncio.create_subprocess_exec(*map(str, args), stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await process.communicate()
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    if process.returncode:
        # Do not log filenames, signed URLs, or entire provider/process output.
        raise MediaError(f'{Path(str(args[0])).name} failed (exit {process.returncode}).')
    return stdout


async def probe(path, max_duration):
    raw = await command('ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', path)
    info = json.loads(raw)
    videos = [s for s in info.get('streams', []) if s['codec_type'] == 'video' and not s.get('disposition', {}).get('attached_pic')]
    audio = next((s for s in info.get('streams', []) if s['codec_type'] == 'audio'), None)
    if not videos or not audio:
        raise MediaError('Upload a video containing an audio track.')
    video = videos[0]
    duration = video.get('duration') or info.get('format', {}).get('duration')
    if video.get('duration_ts') and video.get('time_base'):
        duration = Fraction(video['duration_ts']) * Fraction(video['time_base'])
    else:
        duration = Fraction(str(duration))
    seconds = float(duration)
    if not math.isfinite(seconds) or seconds <= 0 or seconds > max_duration:
        raise MediaError(f'Video duration must be positive and at most {max_duration // 3600} hours.')
    return {'duration_seconds': seconds, 'output_samples': round(duration * OUT_RATE),
            'input_samples': round(duration * IN_RATE), 'audio_index': audio['index'],
            'audio_offset_seconds': float(audio.get('start_time', 0)) - float(video.get('start_time', 0))}


def require_space(directory, bytes_needed):
    if shutil.disk_usage(directory).free < bytes_needed + 64 * 1024 * 1024:
        raise MediaError('Insufficient disk space for this translation.')


async def extract(path, destination, info):
    # Reset stream timestamps, then explicitly preserve the stream's video-relative offset.
    offset = info['audio_offset_seconds']
    filters = ['asetpts=PTS-STARTPTS', 'aresample=16000']
    if offset < 0:
        filters += [f'atrim=start={-offset:.9f}', 'asetpts=PTS-STARTPTS']
    elif offset > 0:
        filters += [f'adelay={round(offset * IN_RATE)}S:all=1']
    filters += ['apad', f'atrim=end_sample={info["input_samples"]}']
    temp = Path(str(destination) + '.part.wav')
    await command('ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', path, '-map', f'0:{info["audio_index"]}',
                  '-vn', '-ac', '1', '-ar', IN_RATE, '-af', ','.join(filters), '-c:a', 'pcm_s16le', temp)
    if wav_samples(temp, IN_RATE) != info['input_samples']:
        raise MediaError('Extracted audio does not match the video timeline.')
    os.replace(temp, destination)


def wav_samples(path, rate=OUT_RATE):
    with wave.open(str(path), 'rb') as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (rate, 1, 2):
            raise MediaError('Unexpected PCM audio format.')
        return audio.getnframes()


def sections(path):
    """Find quiet 100ms boundaries between 90-120s without skipping input samples."""
    with wave.open(str(path), 'rb') as audio:
        total = audio.getnframes()
        start = 0
        while start < total:
            end = min(total, start + 120 * IN_RATE)
            if end < total:
                audio.setpos(start + 90 * IN_RATE)
                quiet = None
                cursor = start + 90 * IN_RATE
                while cursor + 1600 <= end:
                    values = array.array('h', audio.readframes(1600))
                    if sys.byteorder != 'little':
                        values.byteswap()
                    # A full 100ms below -46dBFS qualifies as a quiet split.
                    if values and max(map(abs, values)) <= 164:
                        quiet = cursor + 800
                    cursor += 1600
                if quiet:
                    end = quiet
            yield (start, end)
            start = end


def write_pcm(path, data, rate=OUT_RATE):
    if len(data) % 2:
        raise MediaError('Incomplete PCM sample received.')
    with wave.open(str(path), 'wb') as audio:
        audio.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        audio.writeframes(data)


def atempo_filters(ratio):
    values = []
    while ratio > 2:
        values.append('atempo=2')
        ratio /= 2
    values.append(f'atempo={ratio:.12f}')
    return ','.join(values)


async def fit_audio(raw, fitted, target_samples):
    count = wav_samples(raw)
    if count <= 0:
        raise MediaError('Translation produced no audio.')
    ratio = max(1.0, count / target_samples)
    temp = Path(str(fitted) + '.tempo.wav')
    # Small safety margin accounts for FFmpeg's frame rounding without cropping speech.
    if ratio > 1:
        ratio *= 1.002
        for _ in range(4):
            await command('ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', raw,
                          '-af', atempo_filters(ratio), '-ar', OUT_RATE, '-ac', '1', '-c:a', 'pcm_s16le', temp)
            if wav_samples(temp) <= target_samples:
                break
            ratio *= 1.01
        else:
            raise MediaError('Cannot fit translated speech without cropping it.')
        source = temp
    else:
        source = raw
    actual = wav_samples(source)
    if actual <= 0:
        raise MediaError('Time compression produced no speech samples; refusing silent output.')
    partial = Path(str(fitted) + '.part')
    with wave.open(str(source), 'rb') as src, wave.open(str(partial), 'wb') as dst:
        dst.setparams((1, 2, OUT_RATE, 0, 'NONE', 'not compressed'))
        while data := src.readframes(65536):
            dst.writeframesraw(data)
        remaining = target_samples - actual
        while remaining > 0:
            size = min(remaining, 65536)
            dst.writeframesraw(b'\0' * size * 2)
            remaining -= size
    os.replace(partial, fitted)
    temp.unlink(missing_ok=True)
    return {'speed_ratio': ratio, 'raw_samples': count, 'speech_samples': actual,
            'target_samples': target_samples}


def concatenate(paths, destination, expected_samples):
    partial = Path(str(destination) + '.part')
    with wave.open(str(partial), 'wb') as dst:
        dst.setparams((1, 2, OUT_RATE, 0, 'NONE', 'not compressed'))
        for path in paths:
            with wave.open(str(path), 'rb') as src:
                while data := src.readframes(65536):
                    dst.writeframesraw(data)
    if wav_samples(partial) != expected_samples:
        partial.unlink(missing_ok=True)
        raise MediaError('Final audio duration validation failed.')
    os.replace(partial, destination)


def valid_cues(cues, duration):
    previous = 0
    if not isinstance(cues, list):
        return False
    for cue in cues:
        try:
            start, end = float(cue['start']), float(cue['end'])
            if not (math.isfinite(start) and math.isfinite(end) and previous <= start < end <= duration + 1 / OUT_RATE
                    and round(end * 1000) > round(start * 1000)
                    and isinstance(cue['text'], str) and cue['text'].strip()):
                return False
            previous = end
        except (KeyError, TypeError, ValueError):
            return False
    return True


def timestamp(seconds, vtt=False):
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    secs, ms = divmod(remainder, 1000)
    return f'{hours:02}:{minutes:02}:{secs:02}{"." if vtt else ","}{ms:03}'


def write_subtitles(cues, srt, vtt, duration):
    if not valid_cues(cues, duration):
        raise MediaError('Subtitle timestamps are invalid.')
    for path, web in ((srt, False), (vtt, True)):
        partial = Path(str(path) + '.part')
        with partial.open('w', encoding='utf-8') as output:
            if web:
                output.write('WEBVTT\n\n')
            for index, cue in enumerate(cues, 1):
                text = cue['text'].strip().replace('\r', '').replace('\n\n', '\n')
                output.write(f'{index}\n{timestamp(cue["start"], web)} --> {timestamp(cue["end"], web)}\n{text}\n\n')
        os.replace(partial, path)
