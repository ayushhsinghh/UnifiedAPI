"""Paced, finite Live Translate sessions. Nothing is committed on a failed attempt."""
import asyncio
import wave

from .gemini_media import IN_RATE, OUT_RATE, MediaError, write_pcm


def offset_seconds(value):
    if value is None:
        return None
    if hasattr(value, 'total_seconds'):
        return value.total_seconds()
    if isinstance(value, str):
        return float(value.removesuffix('s'))
    if isinstance(value, (float, int)):
        return float(value)
    if hasattr(value, 'seconds'):
        return value.seconds + getattr(value, 'nanos', 0) / 1e9
    return None


async def translate_section(source, start, end, target_language, raw_path, api_key, model,
                            client_factory=None, paced=True):
    from google import genai
    from google.genai import types

    factory = client_factory or genai.Client
    client = factory(api_key=api_key, http_options={'api_version': 'v1beta'})
    config = types.LiveConnectConfig(
        response_modalities=['AUDIO'],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        translation_config=types.TranslationConfig(target_language_code=target_language, echo_target_language=True))
    output = bytearray()
    transcripts, input_transcripts = [], []
    flushed = asyncio.Event()
    duration = (end - start) / IN_RATE

    try:
        async with client.aio.live.connect(model=model, config=config) as session:
            async def send():
                clock = asyncio.get_running_loop()
                deadline = clock.time()
                with wave.open(str(source), 'rb') as audio:
                    audio.setpos(start)
                    remaining = end - start
                    while remaining:
                        size = min(1600, remaining)
                        data = audio.readframes(size)
                        if len(data) != size * 2:
                            raise MediaError('Input audio ended before its checkpoint boundary.')
                        if paced:
                            await asyncio.sleep(max(0, deadline - clock.time()))
                        await session.send_realtime_input(audio=types.Blob(data=data, mime_type='audio/pcm;rate=16000'))
                        deadline += size / IN_RATE
                        remaining -= size
                await session.send_realtime_input(audio_stream_end=True)
                flushed.set()

            async def receive():
                while True:
                    received = False
                    async for response in session.receive():
                        received = True
                        if getattr(response, 'go_away', None):
                            raise MediaError('Live session ended early; retrying this section.')
                        content = response.server_content
                        if not content:
                            continue
                        if content.interrupted:
                            raise MediaError('Translation was interrupted; section must be retried.')
                        transcript = content.input_transcription
                        if transcript and transcript.text:
                            input_transcripts.append(transcript.text)
                        transcript = content.output_transcription
                        if transcript and transcript.text:
                            transcripts.append({'text': transcript.text,
                                'start': offset_seconds(getattr(transcript, 'start_offset', None)),
                                'end': offset_seconds(getattr(transcript, 'end_offset', None))})
                        if content.model_turn:
                            for part in content.model_turn.parts or []:
                                inline = part.inline_data
                                if inline and inline.data:
                                    mime = inline.mime_type or ''
                                    if not mime.startswith('audio/pcm') or ('rate=' in mime and 'rate=24000' not in mime):
                                        raise MediaError('Live translation returned an unsupported audio format.')
                                    output.extend(inline.data)
                                    if len(output) > (duration + 180) * OUT_RATE * 2 * 4:
                                        raise MediaError('Live translation exceeded the section output limit.')
                        # A flushed final turn is required. Never treat a quiet network as completion.
                        if flushed.is_set() and content.turn_complete:
                            return
                    if not received:
                        raise MediaError('Live session closed before final output completion.')
                    await asyncio.sleep(0)

            send_task = asyncio.create_task(send())
            receive_task = asyncio.create_task(receive())
            try:
                await asyncio.wait_for(asyncio.gather(send_task, receive_task), timeout=duration + 180)
            finally:
                for task in (send_task, receive_task):
                    task.cancel()
                await asyncio.gather(send_task, receive_task, return_exceptions=True)
        if not output:
            raise MediaError('Gemini returned no translated audio for this section.')
        write_pcm(raw_path, bytes(output))
        return {'input_transcript': ''.join(input_transcripts), 'transcripts': transcripts}
    finally:
        await client.aio.aclose()
